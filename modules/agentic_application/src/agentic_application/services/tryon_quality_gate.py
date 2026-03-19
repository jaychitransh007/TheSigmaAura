from __future__ import annotations

import base64
import math
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple


class TryonQualityGate:
    """Assess whether a generated try-on image is safe to surface."""

    def evaluate(
        self,
        *,
        person_image_path: str,
        tryon_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            generated_bytes, generated_mime = self._decode_generated_image(tryon_result)
        except ValueError as exc:
            return self._failed("missing_generated_image", str(exc), [])

        factor_details: List[Dict[str, Any]] = []

        try:
            from PIL import Image, ImageChops, ImageStat
        except ImportError:
            min_bytes_ok = len(generated_bytes) >= 4096
            factor_details.append({
                "factor": "minimum_output_bytes",
                "passed": min_bytes_ok,
                "detail": f"generated_bytes={len(generated_bytes)}",
            })
            if not min_bytes_ok:
                return self._failed("low_quality_output", "Generated try-on output is too small to trust.", factor_details)
            return {
                "passed": True,
                "quality_score_pct": 65,
                "reason_code": "",
                "message": "Passed fallback byte-level checks.",
                "factors": factor_details,
                "mime_type": generated_mime,
            }

        try:
            person_image = Image.open(Path(person_image_path)).convert("RGB")
        except FileNotFoundError:
            return self._failed("missing_person_image", "Person image not found for try-on quality check.", factor_details)
        except Exception as exc:
            return self._failed("invalid_person_image", f"Person image could not be opened: {exc}", factor_details)

        try:
            generated_image = Image.open(BytesIO(generated_bytes)).convert("RGB")
        except Exception as exc:
            return self._failed("invalid_generated_image", f"Generated try-on image could not be opened: {exc}", factor_details)

        person_w, person_h = person_image.size
        generated_w, generated_h = generated_image.size
        max_side = max(generated_w, generated_h)
        aspect_delta = abs((generated_w / max(generated_h, 1)) - (person_w / max(person_h, 1)))

        min_resolution_ok = max_side >= 384 and min(generated_w, generated_h) >= 256
        factor_details.append({
            "factor": "resolution",
            "passed": min_resolution_ok,
            "detail": f"generated={generated_w}x{generated_h}",
        })
        if not min_resolution_ok:
            return self._failed("low_resolution_output", "Generated try-on output resolution is too low.", factor_details)

        aspect_ok = aspect_delta <= 0.35
        factor_details.append({
            "factor": "aspect_ratio_alignment",
            "passed": aspect_ok,
            "detail": f"person={person_w}x{person_h}, generated={generated_w}x{generated_h}, delta={aspect_delta:.3f}",
        })
        if not aspect_ok:
            return self._failed("aspect_ratio_drift", "Generated try-on geometry drifted too far from the source image.", factor_details)

        generated_stat = ImageStat.Stat(generated_image)
        avg_stddev = sum(float(value) for value in generated_stat.stddev[:3]) / 3.0
        detail_ok = avg_stddev >= 12.0
        factor_details.append({
            "factor": "image_detail",
            "passed": detail_ok,
            "detail": f"avg_stddev={avg_stddev:.2f}",
        })
        if not detail_ok:
            return self._failed("low_detail_output", "Generated try-on output lacks enough visual detail.", factor_details)

        resized_person = person_image.resize((384, 384))
        resized_generated = generated_image.resize((384, 384))
        diff = ImageChops.difference(resized_person, resized_generated)
        diff_stat = ImageStat.Stat(diff)
        rms = math.sqrt(sum((float(value) ** 2) for value in diff_stat.rms[:3]) / 3.0)

        changed_enough = rms >= 6.0
        factor_details.append({
            "factor": "visible_change",
            "passed": changed_enough,
            "detail": f"rms_difference={rms:.2f}",
        })
        if not changed_enough:
            return self._failed("no_visible_tryon_change", "Generated try-on output is too close to the original image to trust.", factor_details)

        severe_drift = rms <= 150.0
        factor_details.append({
            "factor": "overall_fidelity",
            "passed": severe_drift,
            "detail": f"rms_difference={rms:.2f}",
        })
        if not severe_drift:
            return self._failed("severe_generation_drift", "Generated try-on output drifted too far from the original image.", factor_details)

        deductions = 0
        deductions += 0 if max_side >= 768 else 10
        deductions += 0 if aspect_delta <= 0.15 else 8
        deductions += 0 if avg_stddev >= 18.0 else 7
        deductions += 0 if rms >= 12.0 else 10
        score_pct = max(0, min(100, 100 - deductions))

        return {
            "passed": True,
            "quality_score_pct": score_pct,
            "reason_code": "",
            "message": "Generated try-on output passed quality checks.",
            "factors": factor_details,
            "mime_type": generated_mime,
        }

    @staticmethod
    def _decode_generated_image(tryon_result: Dict[str, Any]) -> Tuple[bytes, str]:
        data_url = str(tryon_result.get("data_url") or "").strip()
        image_base64 = str(tryon_result.get("image_base64") or "").strip()
        mime_type = str(tryon_result.get("mime_type") or "image/png").strip() or "image/png"

        if data_url.startswith("data:") and ";base64," in data_url:
            header, encoded = data_url.split(",", 1)
            if ":" in header and ";" in header:
                mime_type = header.split(":", 1)[1].split(";", 1)[0].strip() or mime_type
            try:
                return base64.b64decode(encoded), mime_type
            except Exception as exc:
                raise ValueError(f"Could not decode try-on data URL: {exc}") from exc

        if image_base64:
            try:
                return base64.b64decode(image_base64), mime_type
            except Exception as exc:
                raise ValueError(f"Could not decode try-on base64 image: {exc}") from exc

        raise ValueError("No generated try-on image was returned.")

    @staticmethod
    def _failed(reason_code: str, message: str, factors: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "passed": False,
            "quality_score_pct": 0,
            "reason_code": reason_code,
            "message": message,
            "factors": factors,
        }
