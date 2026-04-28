import os
from groq import Groq
import logging

class CaptionGenerator:
    def __init__(self, config):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.logger = logging.getLogger(__name__)
        self.fixed_tag = config['settings'].get('fixed_hashtag', '#BoyishLife')

    def generate(self, filename, media_type):
        clean_name = os.path.splitext(filename)[0].replace('_', ' ')
        
        tag_counts = {
            "video": 4,
            "image": 3
        }
        count = tag_counts.get(media_type, 3)

        system_instruction = (
            "You are a social media manager. Generate a caption based on the filename. "
            f"CRITICAL: End the caption with exactly {count} relevant hashtags based on the filename. "
            "Do NOT add the #BoyishLife hashtag (I will add it myself)."
        )

        prompts = {
            "video": f"Write an engaging, storytelling caption for a video about '{clean_name}'. Max 150 words.",
            "image": f"Write a short, punchy caption for a photo titled '{clean_name}'. Max 100 words."
        }

        user_prompt = prompts.get(media_type, prompts['image'])

        try:
            completion = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            raw_caption = completion.choices[0].message.content.strip().replace('"', '').replace("'", "")

            parts = raw_caption.split('#')
            main_text = parts[0].strip()

            hashtags = []
            for p in parts[1:]:
                tag = p.split()[0].strip().replace(',', '').replace('.', '')
                if len(tag) > 1:
                    hashtags.append(tag)

            return {
                "text": main_text,
                "tags": hashtags,
                "brand_tag": self.fixed_tag
            }

        except Exception as e:
            self.logger.error(f"AI Generation Failed: {e}")
            return {
                "text": clean_name,
                "tags": ["nature", "life"],
                "brand_tag": self.fixed_tag
            }
