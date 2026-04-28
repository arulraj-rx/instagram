import logging
import os

from groq import Groq


class CaptionGenerator:
    def __init__(self, config):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.logger = logging.getLogger(__name__)
        self.fixed_tag = str(config.get("fixed_hashtag", "#arul9x")).strip()
        self.caption_limit = int(config.get("caption_limit", 2200))
        self.threads_caption_limit = int(
            config.get("threads_caption_limit", self.caption_limit)
        )

    def generate(self, filename, media_type, platform="instagram"):
        clean_name = self._clean_name(filename)
        platform = str(platform).strip().lower()

        if platform == "threads":
            return self._generate_threads_caption(clean_name, media_type)
        return self._generate_instagram_caption(clean_name, media_type)

    def _generate_instagram_caption(self, clean_name, media_type):
        hashtag_target = 4 if media_type == "video" else 3
        system_instruction = (
            "You write Instagram captions from filenames. "
            "Write in 3 short sections with a blank line between sections. "
            "Use natural expressive emojis based on the emotion of the post, maximum 10 emojis total. "
            f"End with exactly {hashtag_target} relevant hashtags on the final line. "
            "Do not add quotation marks. "
            f"Do not add the fixed hashtag {self.fixed_tag}; it will be appended separately."
        )

        if media_type == "video":
            user_prompt = (
                f"Create an Instagram Reel caption for '{clean_name}'. "
                "Keep it catchy, emotional, and natural. Max 90 words."
            )
        else:
            user_prompt = (
                f"Create an Instagram photo caption for '{clean_name}'. "
                "Keep it warm, engaging, and natural. Max 70 words."
            )

        try:
            completion = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.8,
                max_tokens=500,
            )
            raw_caption = completion.choices[0].message.content.strip()
            normalized = self._normalize_multiline_caption(raw_caption)
            return self._append_fixed_hashtag(normalized)
        except Exception as error:
            self.logger.error(f"AI generation failed: {error}")
            fallback = self._normalize_multiline_caption(clean_name)
            return self._append_fixed_hashtag(fallback)

    def _generate_threads_caption(self, clean_name, media_type):
        system_instruction = (
            "You write Threads captions from filenames. "
            "Write in 3 or 4 short lines or short paragraphs with blank lines between them. "
            "Use emotional emojis that fit the post, maximum 10 emojis total. "
            "Do not use hashtags at all. "
            "Do not add quotation marks. "
            "Make it feel human, reflective, and suited for Threads."
        )

        if media_type == "video":
            user_prompt = (
                f"Create a Threads caption for the video '{clean_name}'. "
                "Keep it thoughtful and scroll-stopping. Max 80 words."
            )
        else:
            user_prompt = (
                f"Create a Threads caption for the image '{clean_name}'. "
                "Keep it thoughtful and warm. Max 65 words."
            )

        try:
            completion = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.85,
                max_tokens=400,
            )
            raw_caption = completion.choices[0].message.content.strip()
            return self._normalize_multiline_caption(raw_caption)
        except Exception as error:
            self.logger.error(f"Threads AI generation failed: {error}")
            return self._normalize_multiline_caption(clean_name)

    def _clean_name(self, filename):
        return os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").strip()

    def _normalize_multiline_caption(self, caption):
        text = str(caption).replace('"', "").replace("'", "")
        lines = [self._clean_line(line) for line in text.splitlines()]

        cleaned = []
        previous_blank = False
        for line in lines:
            if not line:
                if not previous_blank and cleaned:
                    cleaned.append("")
                previous_blank = True
                continue
            cleaned.append(line)
            previous_blank = False

        return "\n".join(cleaned).strip()

    def _clean_line(self, line):
        return " ".join(str(line).split()).strip()

    def _append_fixed_hashtag(self, caption):
        if not self.fixed_tag:
            return caption[: self.caption_limit].strip()

        combined = f"{caption}\n\n{self.fixed_tag}".strip()
        return combined[: self.caption_limit].strip()
