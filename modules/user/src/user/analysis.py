import base64
import json
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI
from user_profiler.config import get_api_key

from .draping import DigitalDrapingService
from .interpreter import derive_interpretations
from .repository import (
    ANALYSIS_ATTRIBUTE_COLUMN_PREFIXES,
    INTERPRETATION_COLUMN_PREFIXES,
    OnboardingRepository,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        if (base / "prompt").exists():
            return base
    raise FileNotFoundError("Could not locate repo root containing prompt directory.")


PROMPT_DIR = _repo_root() / "prompt"

# Draping collaboration threshold: draping only overrides the deterministic
# season when its confidence margin exceeds this value. Three Strong rounds
# score 9 points (margin ~9), three Slight rounds score 3 (margin ~3).
# Threshold of 4 means roughly two Strong + one Moderate agreement required.
_DRAPING_OVERRIDE_MARGIN = 4


def _apply_draping_collaboration(
    derived: Dict[str, Any],
    draping_result: "DrapingResult",
) -> None:
    """Apply draping result to SeasonalColorGroup using threshold-based collaboration.

    - margin > _DRAPING_OVERRIDE_MARGIN: draping overrides deterministic season
    - margin <= threshold AND draping agrees: deterministic holds, confidence boosted
    - margin <= threshold AND draping disagrees: deterministic holds, draping stored as secondary
    """
    if not draping_result.selected_groups:
        return

    deterministic = derived.get("SeasonalColorGroup", {})
    det_season = deterministic.get("value", "")
    draping_season = draping_result.selected_groups[0]["value"]
    margin = draping_result.confidence_margin

    if margin > _DRAPING_OVERRIDE_MARGIN:
        # Strong draping signal — override
        derived["SeasonalColorGroup"] = {
            **deterministic,
            "value": draping_season,
            "confidence": draping_result.selected_groups[0]["probability"],
            "evidence_note": f"Digital draping override (margin {margin}): {', '.join(g['value'] for g in draping_result.selected_groups)}",
            "source_agent": "digital_draping",
            "additional_groups": draping_result.selected_groups[1:],
            "distribution": draping_result.distribution,
            "confidence_margin": margin,
            "secondary_season": draping_result.selected_groups[1]["value"] if len(draping_result.selected_groups) > 1 else None,
        }
    elif draping_season == det_season:
        # Agreement — boost confidence
        boosted = min(0.99, float(deterministic.get("confidence", 0.5)) + 0.08)
        derived["SeasonalColorGroup"] = {
            **deterministic,
            "confidence": boosted,
            "evidence_note": deterministic.get("evidence_note", "") + f" Confirmed by draping (margin {margin}).",
            "source_agent": "deterministic_confirmed_by_draping",
            "distribution": draping_result.distribution,
            "confidence_margin": margin,
            "secondary_season": draping_result.selected_groups[1]["value"] if len(draping_result.selected_groups) > 1 else None,
        }
    else:
        # Disagreement but weak draping — deterministic holds, draping is secondary
        derived["SeasonalColorGroup"] = {
            **deterministic,
            "evidence_note": deterministic.get("evidence_note", "") + f" Draping suggested {draping_season} (margin {margin}) but deferred to attribute analysis.",
            "source_agent": "deterministic_draping_deferred",
            "additional_groups": draping_result.selected_groups,
            "distribution": draping_result.distribution,
            "confidence_margin": margin,
            "secondary_season": draping_season,
        }


@dataclass(frozen=True)
class AgentSpec:
    agent_name: str
    prompt_filename: str
    attribute_enums: Dict[str, List[str]]
    required_profile_fields: List[str]
    image_categories: List[str]


BODY_TYPE_SPEC = AgentSpec(
    agent_name="body_type_analysis",
    prompt_filename="body_type_analysis.md",
    attribute_enums={
        "ShoulderToHipRatio": [
            "Shoulders Much Wider",
            "Shoulders Slightly Wider",
            "Approximately Equal",
            "Hips Slightly Wider",
            "Hips Much Wider",
        ],
        "TorsoToLegRatio": ["Long Torso / Short Legs", "Balanced", "Short Torso / Long Legs"],
        "BodyShape": ["Hourglass", "Pear", "Inverted Triangle", "Rectangle", "Apple", "Diamond", "Trapezoid"],
        "VisualWeight": ["Light", "Medium-Light", "Medium", "Medium-Heavy", "Heavy"],
        "VerticalProportion": ["Compact", "Moderate", "Elongated"],
        "ArmVolume": ["Slim", "Medium", "Full"],
        "MidsectionState": ["Flat", "Moderate Fullness", "Significant Fullness"],
        "BustVolume": ["Flat / Minimal", "Small", "Medium", "Prominent", "Very Prominent"],
    },
    required_profile_fields=["gender", "date_of_birth", "height_cm", "waist_cm"],
    image_categories=["full_body"],
)

COLOR_HEADSHOT_SPEC = AgentSpec(
    agent_name="color_analysis_headshot",
    prompt_filename="color_analysis_headshot.md",
    attribute_enums={
        "SkinSurfaceColor": ["Fair", "Light", "Medium", "Tan", "Dark", "Deep"],
        "HairColor": ["Black", "Dark Brown", "Medium Brown", "Light Brown", "Auburn", "Red", "Blonde", "Grey", "White"],
        "HairColorTemperature": ["Cool", "Neutral", "Warm"],
        "EyeColor": ["Black-Brown", "Dark Brown", "Medium Brown", "Light Brown", "Hazel", "Green", "Blue", "Grey"],
        "EyeChroma": ["Soft / Muted", "Balanced", "Bright / Clear"],
        "SkinUndertone": ["Warm", "Cool", "Neutral-Warm", "Neutral-Cool", "Olive"],
        "SkinChroma": ["Muted", "Moderate", "Clear"],
    },
    required_profile_fields=["gender", "date_of_birth"],
    image_categories=["headshot"],
)

OTHER_DETAILS_SPEC = AgentSpec(
    agent_name="other_details_analysis",
    prompt_filename="other_details_analysis.md",
    attribute_enums={
        "FaceShape": ["Oval", "Round", "Square", "Rectangle", "Oblong", "Heart", "Diamond", "Triangle"],
        "NeckLength": ["Short", "Average", "Long"],
        "HairLength": ["Cropped", "Short", "Medium", "Long"],
        "JawlineDefinition": ["Soft", "Balanced", "Sharp"],
        "ShoulderSlope": ["Square", "Average", "Sloped"],
    },
    required_profile_fields=["gender", "date_of_birth"],
    image_categories=["headshot", "full_body"],
)

ALL_AGENT_SPECS = [
    BODY_TYPE_SPEC,
    COLOR_HEADSHOT_SPEC,
    OTHER_DETAILS_SPEC,
]
AGENT_SPEC_BY_NAME = {spec.agent_name: spec for spec in ALL_AGENT_SPECS}


class UserAnalysisService:
    def __init__(
        self,
        repo: OnboardingRepository,
        *,
        model: str = "gpt-5.4",
        reasoning_effort: str = "high",
    ) -> None:
        self._repo = repo
        self._model = model
        self._reasoning_effort = reasoning_effort

    # ── Phased analysis — run individual agents as data becomes available ──

    def run_single_agent(
        self,
        user_id: str,
        agent_name: str,
        *,
        prompt_context_override: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Run one analysis agent and persist its output on the snapshot.

        Does NOT collate, interpret, or drape — that happens in the final
        phase when all 3 agents have completed. If no snapshot exists, one
        is created in 'running' state.
        """
        spec = AGENT_SPEC_BY_NAME.get(agent_name)
        if not spec:
            raise ValueError(f"Unknown agent: {agent_name}")

        run = self.ensure_analysis_started(user_id)
        run_id = str(run["id"])
        if run.get("status") == "pending":
            self._repo.update_analysis_snapshot(run_id, status="running", started_at=_now_iso(), error_message="")

        images = {row["category"]: row for row in self._repo.get_images(user_id)}
        missing_imgs = [c for c in spec.image_categories if c not in images]
        if missing_imgs:
            raise ValueError(f"Missing images for {agent_name}: {', '.join(missing_imgs)}")

        api_key = get_api_key()
        if prompt_context_override is not None:
            ctx = prompt_context_override
        else:
            profile = self._repo.get_profile_by_user_id(user_id)
            age = self._calculate_age((profile or {}).get("date_of_birth"))
            ctx = {
                "gender": (profile or {}).get("gender") or "",
                "age": age,
                "height": (profile or {}).get("height_cm") or "",
                "waist": (profile or {}).get("waist_cm") or "",
            }

        output = self._run_agent(api_key, spec, ctx, images)

        # Persist to the correct column on the snapshot
        update_kwargs: Dict[str, Any] = {}
        if agent_name == "body_type_analysis":
            update_kwargs["body_type_output"] = output
        elif agent_name == "color_analysis_headshot":
            update_kwargs["color_headshot_output"] = output
        elif agent_name == "other_details_analysis":
            update_kwargs["other_details_output"] = output
        if update_kwargs:
            self._repo.update_analysis_snapshot(run_id, **update_kwargs)

        return output

    def run_remaining_and_finalize(self, user_id: str) -> Dict[str, Any]:
        """Run any agents not yet completed, then collate + interpret + drape.

        Safe to call even if all agents already ran (it skips them).
        This is the final phase that produces derived_interpretations.
        """
        run = self.ensure_analysis_started(user_id)
        run_id = str(run["id"])
        if run.get("status") == "completed":
            return self.get_analysis_status(user_id)

        self._repo.update_analysis_snapshot(run_id, status="running", started_at=_now_iso(), error_message="")
        profile, images, api_key, prompt_context = self._analysis_inputs(user_id)

        # Check which agents already have output
        existing_outputs: Dict[str, Dict[str, Any]] = {}
        if run.get("body_type_output"):
            existing_outputs["body_type_analysis"] = run["body_type_output"]
        if run.get("color_headshot_output"):
            existing_outputs["color_analysis_headshot"] = run["color_headshot_output"]
        if run.get("other_details_output"):
            existing_outputs["other_details_analysis"] = run["other_details_output"]

        # Run missing agents in parallel
        missing_specs = [s for s in ALL_AGENT_SPECS if s.agent_name not in existing_outputs]
        if missing_specs:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    spec.agent_name: executor.submit(self._run_agent, api_key, spec, prompt_context, images)
                    for spec in missing_specs
                }
                for name, future in futures.items():
                    existing_outputs[name] = future.result()

        # Collate all 3
        collated = self._collate_outputs(existing_outputs)
        derived = derive_interpretations(
            collated["attributes"],
            height_cm=float(profile.get("height_cm") or 0.0),
            waist_cm=float(profile.get("waist_cm") or 0.0),
        )

        # Digital draping with threshold-based collaboration
        draping_service = DigitalDrapingService(self._repo, model=self._model)
        draping_result = draping_service.run_draping(
            user_id, images["headshot"]["file_path"], collated["attributes"]
        )
        _apply_draping_collaboration(derived, draping_result)

        self._repo.update_analysis_snapshot(
            run_id,
            status="completed",
            completed_at=_now_iso(),
            error_message="",
            body_type_output=existing_outputs.get("body_type_analysis", {}),
            color_headshot_output=existing_outputs.get("color_analysis_headshot", {}),
            other_details_output=existing_outputs.get("other_details_analysis", {}),
            collated_output={**collated, "derived_interpretations": derived},
            draping_output=draping_result.to_dict(),
        )
        self._repo.insert_interpretation_snapshot(
            user_id=user_id,
            analysis_snapshot_id=run_id,
            interpretations=derived,
        )
        self._repo.insert_effective_seasonal_groups(
            user_id=user_id,
            seasonal_groups=draping_result.selected_groups,
            source="draping" if draping_result.selected_groups else "deterministic",
        )
        return self.get_analysis_status(user_id)

    def ensure_analysis_started(self, user_id: str) -> Dict[str, Any]:
        latest = self._repo.get_latest_analysis_snapshot(user_id)
        if latest and latest.get("status") in {"pending", "running", "completed"}:
            return latest
        return self._repo.create_analysis_snapshot(
            user_id=user_id,
            status="pending",
            model_name=self._model,
        )

    def force_analysis_restart(self, user_id: str) -> Dict[str, Any]:
        return self._repo.create_analysis_snapshot(
            user_id=user_id,
            status="pending",
            model_name=self._model,
        )

    def force_agent_restart(self, user_id: str, agent_name: str) -> Dict[str, Any]:
        if agent_name not in AGENT_SPEC_BY_NAME:
            raise ValueError("Unknown analysis agent.")
        baseline = self._repo.get_latest_analysis_snapshot(user_id)
        run = self._repo.create_analysis_snapshot(
            user_id=user_id,
            status="pending",
            model_name=self._model,
        )
        if baseline:
            self._repo.update_analysis_snapshot(
                str(run["id"]),
                body_type_output=baseline.get("body_type_output") or {},
                color_headshot_output=baseline.get("color_headshot_output") or {},
                other_details_output=baseline.get("other_details_output") or {},
                collated_output=baseline.get("collated_output") or {},
            )
        return run

    def run_analysis(self, user_id: str) -> Dict[str, Any]:
        run = self.ensure_analysis_started(user_id)
        run_id = str(run["id"])
        self._repo.update_analysis_snapshot(run_id, status="running", started_at=_now_iso(), error_message="")

        profile, images, api_key, prompt_context = self._analysis_inputs(user_id)

        # Run required agents in parallel
        specs_to_run = list(ALL_AGENT_SPECS)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                spec.agent_name: executor.submit(self._run_agent, api_key, spec, prompt_context, images)
                for spec in specs_to_run
            }
            agent_outputs = {name: future.result() for name, future in futures.items()}

        collated = self._collate_outputs(agent_outputs)
        derived = derive_interpretations(
            collated["attributes"],
            height_cm=float(profile.get("height_cm") or 0.0),
            waist_cm=float(profile.get("waist_cm") or 0.0),
        )

        # Digital draping with threshold-based collaboration
        draping_service = DigitalDrapingService(self._repo, model=self._model)
        draping_result = draping_service.run_draping(
            user_id, images["headshot"]["file_path"], collated["attributes"]
        )
        _apply_draping_collaboration(derived, draping_result)

        self._repo.update_analysis_snapshot(
            run_id,
            status="completed",
            completed_at=_now_iso(),
            error_message="",
            body_type_output=agent_outputs["body_type_analysis"],
            color_headshot_output=agent_outputs["color_analysis_headshot"],
            other_details_output=agent_outputs["other_details_analysis"],
            collated_output={**collated, "derived_interpretations": derived},
            draping_output=draping_result.to_dict(),
        )
        self._repo.insert_interpretation_snapshot(
            user_id=user_id,
            analysis_snapshot_id=run_id,
            interpretations=derived,
        )
        # Persist effective seasonal groups
        self._repo.insert_effective_seasonal_groups(
            user_id=user_id,
            seasonal_groups=draping_result.selected_groups,
            source="draping" if draping_result.selected_groups else "deterministic",
        )
        return self.get_analysis_status(user_id)

    def run_agent_rerun(self, user_id: str, agent_name: str, *, run_id: str) -> Dict[str, Any]:
        spec = AGENT_SPEC_BY_NAME.get(agent_name)
        if spec is None:
            raise ValueError("Unknown analysis agent.")
        baseline = self._repo.get_previous_analysis_snapshot(user_id, run_id) or {}
        self._repo.update_analysis_snapshot(run_id, status="running", started_at=_now_iso(), error_message="")

        profile, images, api_key, prompt_context = self._analysis_inputs(user_id)
        agent_outputs = {
            "body_type_analysis": baseline.get("body_type_output") or {},
            "color_analysis_headshot": baseline.get("color_headshot_output") or {},
            "other_details_analysis": baseline.get("other_details_output") or {},
        }
        agent_outputs[agent_name] = self._run_agent(api_key, spec, prompt_context, images)

        collated = self._collate_outputs(agent_outputs)
        derived = derive_interpretations(
            collated["attributes"],
            height_cm=float(profile.get("height_cm") or 0.0),
            waist_cm=float(profile.get("waist_cm") or 0.0),
        )
        self._repo.update_analysis_snapshot(
            run_id,
            status="completed",
            completed_at=_now_iso(),
            error_message="",
            body_type_output=agent_outputs["body_type_analysis"],
            color_headshot_output=agent_outputs["color_analysis_headshot"],
            other_details_output=agent_outputs["other_details_analysis"],
            collated_output={**collated, "derived_interpretations": derived},
        )
        self._repo.insert_interpretation_snapshot(
            user_id=user_id,
            analysis_snapshot_id=run_id,
            interpretations=derived,
        )
        return self.get_analysis_status(user_id)

    def fail_analysis(self, user_id: str, message: str) -> Dict[str, Any]:
        latest = self._repo.get_latest_analysis_snapshot(user_id)
        if latest:
            self._repo.update_analysis_snapshot(
                str(latest["id"]),
                status="failed",
                completed_at=_now_iso(),
                error_message=message,
            )
        return self.get_analysis_status(user_id)

    def _analysis_inputs(self, user_id: str) -> tuple[Dict[str, Any], Dict[str, Dict[str, Any]], str, Dict[str, Any]]:
        profile = self._repo.get_profile_by_user_id(user_id)
        if not profile:
            raise ValueError("User not found.")
        images = {row["category"]: row for row in self._repo.get_images(user_id)}
        missing_categories = [category for category in ("full_body", "headshot") if category not in images]
        if missing_categories:
            raise ValueError(f"Missing required onboarding images: {', '.join(missing_categories)}")
        api_key = get_api_key()
        age = self._calculate_age(profile.get("date_of_birth"))
        prompt_context = {
            "gender": profile.get("gender") or "prefer_not_to_say",
            "age": age,
            "height": profile.get("height_cm") or "",
            "waist": profile.get("waist_cm") or "",
        }
        return profile, images, api_key, prompt_context

    def get_analysis_status(self, user_id: str) -> Dict[str, Any]:
        latest = self._repo.get_latest_analysis_snapshot(user_id)
        profile = self._repo.get_profile_by_user_id(user_id)
        latest_style_preference = self._repo.get_latest_style_preference_snapshot(user_id)
        latest_analysis_snapshot = self._repo.get_latest_analysis_snapshot(user_id)
        latest_interpretation_snapshot = (
            self._repo.get_interpretation_snapshot_for_analysis(str(latest_analysis_snapshot["id"]))
            if latest_analysis_snapshot
            else None
        )
        if not latest:
            return {
                "user_id": user_id,
                "status": "not_started",
                "analysis_run_id": "",
                "error_message": "",
                "profile": self._profile_summary(profile, latest_style_preference),
                "agent_outputs": {},
                "attributes": {},
                "grouped_attributes": {},
                "derived_interpretations": {},
            }
        agent_outputs = {
            "body_type_analysis": latest.get("body_type_output") or {},
            "color_analysis_headshot": latest.get("color_headshot_output") or {},
            "other_details_analysis": latest.get("other_details_output") or {},
        }
        collated = (latest_analysis_snapshot or {}).get("collated_output") or latest.get("collated_output") or {}
        attributes = collated.get("attributes") or self._flatten_analysis_snapshot(latest_analysis_snapshot)
        grouped_attributes = collated.get("grouped_attributes") or self._group_current_outputs(agent_outputs, attributes)
        derived = collated.get("derived_interpretations") or self._flatten_interpretation_snapshot(latest_interpretation_snapshot)
        return {
            "user_id": user_id,
            "status": str(latest.get("status") or "not_started"),
            "analysis_run_id": str(latest.get("id") or ""),
            "error_message": str(latest.get("error_message") or ""),
            "profile": self._profile_summary(profile, latest_style_preference),
            "agent_outputs": agent_outputs,
            "attributes": attributes,
            "grouped_attributes": grouped_attributes,
            "derived_interpretations": derived,
        }

    def _run_agent(
        self,
        api_key: str,
        spec: AgentSpec,
        prompt_context: Dict[str, Any],
        images: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        prompt = self._render_prompt(spec, prompt_context)
        client = OpenAI(api_key=api_key)
        user_content: List[Dict[str, Any]] = [
            {"type": "input_text", "text": "Analyze the provided onboarding images and return the required JSON."}
        ]
        for image_url in self._image_urls_for_agent(spec, images):
            user_content.append({"type": "input_image", "image_url": image_url})
        response = client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                {"role": "user", "content": user_content},
            ],
            reasoning={"effort": self._reasoning_effort},
            text={"format": self._response_format(spec)},
        )
        return self._extract_response_json(response)

    def _render_prompt(self, spec: AgentSpec, context: Dict[str, Any]) -> str:
        prompt = (PROMPT_DIR / spec.prompt_filename).read_text(encoding="utf-8").strip()
        replacements = {
            "<gender>": str(context.get("gender") or ""),
            "<age>": str(context.get("age") or ""),
            "<height>": str(context.get("height") or ""),
            "<waist>": str(context.get("waist") or ""),
        }
        for key, value in replacements.items():
            prompt = prompt.replace(key, value)
        return prompt

    def _response_format(self, spec: AgentSpec) -> Dict[str, Any]:
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for attribute_name, enum_values in spec.attribute_enums.items():
            properties[attribute_name] = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "value": {"type": "string", "enum": list(enum_values) + ["Unable to Assess"]},
                    "confidence": {"type": "number"},
                    "evidence_note": {"type": "string"},
                },
                "required": ["value", "confidence", "evidence_note"],
            }
            required.append(attribute_name)
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": required,
        }
        return {
            "type": "json_schema",
            "name": spec.agent_name,
            "strict": True,
            "schema": schema,
        }

    def _image_urls_for_agent(self, spec: AgentSpec, images: Dict[str, Dict[str, Any]]) -> List[str]:
        urls: List[str] = []
        for category in spec.image_categories:
            urls.append(self._image_to_input_url(images[category]["file_path"]))
        return urls

    def _extract_response_json(self, response: Any) -> Dict[str, Any]:
        output_text = getattr(response, "output_text", "") or ""
        if output_text:
            return json.loads(output_text)
        payload = response.model_dump() if hasattr(response, "model_dump") else {}
        for block in payload.get("output", []) or []:
            for content in block.get("content", []) or []:
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return json.loads(text)
        raise ValueError("No parseable JSON returned by model.")

    def _collate_outputs(self, outputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        attributes: Dict[str, Dict[str, Any]] = {}
        grouped: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for agent_name, payload in outputs.items():
            grouped[agent_name] = {}
            for attribute_name, values in payload.items():
                attribute_payload = {
                    "value": values["value"],
                    "confidence": float(values["confidence"]),
                    "evidence_note": values["evidence_note"],
                    "source_agent": agent_name,
                }
                attributes[attribute_name] = attribute_payload
                grouped[agent_name][attribute_name] = attribute_payload
        return {"attributes": attributes, "grouped_attributes": grouped}

    def _flatten_analysis_snapshot(self, row: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if not row:
            return {}
        agent_outputs = {
            "body_type_analysis": row.get("body_type_output") or {},
            "color_analysis_headshot": row.get("color_headshot_output") or {},
            "other_details_analysis": row.get("other_details_output") or {},
        }
        flattened: Dict[str, Dict[str, Any]] = {}
        for attribute_name, prefix in ANALYSIS_ATTRIBUTE_COLUMN_PREFIXES.items():
            value = row.get(f"{prefix}_value") or ""
            if not value:
                continue
            flattened[attribute_name] = {
                "value": value,
                "confidence": float(row.get(f"{prefix}_confidence") or 0.0),
                "evidence_note": row.get(f"{prefix}_evidence_note") or "",
                "source_agent": self._source_agent_for_attribute(attribute_name, agent_outputs),
            }
        return flattened

    def _flatten_interpretation_snapshot(self, row: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if not row:
            return {}
        flattened: Dict[str, Dict[str, Any]] = {}
        for interpretation_name, prefix in INTERPRETATION_COLUMN_PREFIXES.items():
            value = row.get(f"{prefix}_value") or ""
            if not value:
                continue
            flattened[interpretation_name] = {
                "value": value,
                "confidence": float(row.get(f"{prefix}_confidence") or 0.0),
                "evidence_note": row.get(f"{prefix}_evidence_note") or "",
                "source_agent": "deterministic_interpreter",
            }
        return flattened

    def _group_current_outputs(
        self,
        agent_outputs: Dict[str, Dict[str, Any]],
        flattened_attributes: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        grouped: Dict[str, Dict[str, Dict[str, Any]]] = {
            "body_type_analysis": {},
            "color_analysis_headshot": {},
            "other_details_analysis": {},
        }
        for attribute_name, payload in flattened_attributes.items():
            grouped.setdefault(str(payload.get("source_agent") or "unknown"), {})
            grouped[str(payload.get("source_agent") or "unknown")][attribute_name] = payload
        for agent_name, output in agent_outputs.items():
            if not grouped.get(agent_name):
                grouped[agent_name] = {}
                for attribute_name, payload in output.items():
                    grouped[agent_name][attribute_name] = {
                        "value": payload.get("value", ""),
                        "confidence": float(payload.get("confidence") or 0.0),
                        "evidence_note": payload.get("evidence_note", ""),
                        "source_agent": agent_name,
                    }
        return grouped

    def _source_agent_for_attribute(self, attribute_name: str, agent_outputs: Dict[str, Dict[str, Any]]) -> str:
        for agent_name, payload in agent_outputs.items():
            if attribute_name in payload:
                return agent_name
        return "unknown"

    def _profile_summary(self, profile: Optional[Dict[str, Any]], style_preference: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not profile:
            return {}
        return {
            "mobile": profile.get("mobile", ""),
            "name": profile.get("name", ""),
            "date_of_birth": str(profile.get("date_of_birth") or ""),
            "gender": profile.get("gender", ""),
            "height_cm": profile.get("height_cm"),
            "waist_cm": profile.get("waist_cm"),
            "profession": profile.get("profession", ""),
            "style_preference": {
                "primaryArchetype": (style_preference or {}).get("primary_archetype", ""),
                "secondaryArchetype": (style_preference or {}).get("secondary_archetype"),
                "riskTolerance": (style_preference or {}).get("risk_tolerance", ""),
                "formalityLean": (style_preference or {}).get("formality_lean", ""),
                "patternType": (style_preference or {}).get("pattern_type", ""),
            },
        }

    def _calculate_age(self, raw_date: Any) -> int:
        if not raw_date:
            return 0
        if isinstance(raw_date, date):
            birth_date = raw_date
        else:
            birth_date = date.fromisoformat(str(raw_date))
        today = date.today()
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

    def _image_to_input_url(self, image_ref: str) -> str:
        path = Path(image_ref).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image file not found: {image_ref}")
        mime, _ = mimetypes.guess_type(str(path))
        if not mime:
            mime = "image/jpeg"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"

