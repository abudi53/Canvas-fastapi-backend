# from huggingface_hub import InferenceClient
from google import genai
from google.genai import types
import base64
import os
import logging
from fastapi import HTTPException
# import asyncio  # Import asyncio for the test

# Remove global client initialization
# client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


# Docs: Generate Image on bytes, encode it to base64, and return it as a string
# https://ai.google.dev/gemini-api/docs/image-generation


async def generate_image_service(prompt: str) -> str:
    # Initialize client inside the function
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    prompt_template: str = "Generate an image of a {prompt}."
    logging.info(f"Generating image for prompt: {prompt}")

    # Add logging before the call
    logging.info("Attempting to call client.aio.models.generate_content")
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash-exp-image-generation",
            contents=prompt_template.format(prompt=prompt),
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        # Add logging after the call
        logging.info(
            f"Response received successfully: {response.candidates[0].finish_reason if response.candidates else 'No candidates'}"
        )  # Log finish reason or indicate no candidates
    except Exception as e:
        logging.error(
            f"Error during generate_content call: {e}", exc_info=True
        )  # Log full exception
        # Re-raise the exception or handle it appropriately
        raise HTTPException(
            status_code=500, detail=f"Google GenAI API call failed: {e}"
        )

    if not response.candidates:
        logging.warning("No candidates found in the response.")
        return "No image data found in the response."

    for part in response.candidates[0].content.parts:  # type: ignore
        if part.inline_data is not None:
            base64encoded_image = base64.b64encode(part.inline_data.data).decode(  # type: ignore
                "utf-8"
            )
            return base64encoded_image

    logging.warning("No inline_data found in response parts.")
    return "No image data found in the response."


####### HUGGING FACE MODEL INFERENCE #######

# client = InferenceClient(
#     provider="hf-inference",
#     api_key=os.getenv("HF_API_KEY"),
# )
#
# def generate_image_service(prompt: str) -> str:
#     """Generate an image based on a prompt."""
#     PROMPT_TEMPLATE: str = "Generate an image of a {prompt}."
#     response_bytes: bytes = client.post(
#         json={
#             "inputs": PROMPT_TEMPLATE.format(prompt=prompt),
#             "parameters": {  # Parameters might vary slightly depending on the model endpoint
#                 "width": 512,
#                 "height": 512,
#             },
#         },
#         model="black-forest-labs/FLUX.1-dev",
#         task="text-to-image",  # Specify the task for the post request
#     )

#     img_string = base64.b64encode(response_bytes).decode("utf-8")

#     return img_string  # To return the raw bytes
