from google import genai
from google.genai import types
import os

client = genai.Client(
    vertexai=True,
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"],
)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Reply with: Vertex AI is working."
)

print(response.text)