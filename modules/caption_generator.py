import logging
import os

from groq import Groq


class CaptionGenerator:
    def __init__(self, config):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.logger = logging.getLogger(__name__)
        self.fixed_tag = str(config.get("fixed_hashtag", "#BoyishLife")).strip()
        self.caption_limit = int(config.get("caption_limit", 2200))

    def generate(self, filename, media_type):
        clean_name = self._clean_name(filename)
        hashtag_target = 4 if media_type == "video" else 3

        system_instruction = (
            "You write Instagram captions from filenames. "
            f"End with exactly {hashtag_target} relevant hashtags. "
            "Do not add quotation marks. "
            f"Do not add the fixed hashtag {self.fixed_tag}; it will be appended separately."
        )

        if media_type == "video":
            user_prompt = (
                f"Create an Instagram Reel caption for '{clean_name}'. "
                "Keep it catchy and natural. Max 90 words."
            )
        else:
            user_prompt = (
                f"Create an Instagram photo caption for '{clean_name}'. "
                "Keep it clean and engaging. Max 70 words."
            )

        try:
            completion = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )
            raw_caption = completion.choices[0].message.content.strip()
            normalized = self._normalize_caption(raw_caption)
            return self._append_fixed_hashtag(normalized)
        except Exception as error:
            self.logger.error(f"AI generation failed: {error}")
            return self._append_fixed_hashtag(clean_name)

    def _clean_name(self, filename):
        return os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").strip()

    def _normalize_caption(self, caption):
        return " ".join(caption.replace('"', "").replace("'", "").split())

    def _append_fixed_hashtag(self, caption):
        if not self.fixed_tag:
            return caption[: self.caption_limit].strip()

        combined = f"{caption}\n\n{self.fixed_tag}".strip()
        return combined[: self.caption_limit].strip()
