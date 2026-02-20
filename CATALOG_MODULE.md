How GPT 5 nano model can be used in Batch mode to extract garment details from  image url? How do I run batch API to use GPT 5 nano model:
  1. I have a CSV of catalog with products - name, description, store, image url, url, price
  2. I need The system to derive 22 attributes for each product row using description and image url
  3. Save back to CSV.

  How will this work?

  High-Level Flow

  Input CSV
     ↓
  Generate JSONL batch file (1 request per product)
     ↓
  Upload file → Create Batch Job
     ↓
  Wait for completion
     ↓
  Download output file
     ↓
  Merge responses back to original CSV
     ↓
  Export enriched CSV


System prompt:
"""
You are a precision garment analyst trained to extract body-fit and silhouette attributes from fashion product images. You return structured JSON only. You never guess — when uncertain, you lower confidence and return the most defensible value.
"""


User prompt:
"""

"""