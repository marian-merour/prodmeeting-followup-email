"""Claude-based meeting notes parser."""

import json
from dataclasses import dataclass, field
from typing import Optional

import anthropic


@dataclass
class MeetingData:
    """Structured data extracted from meeting notes."""

    artist_first_name: str
    artist_email: str
    course_subject: str
    outline_delivery_date: Optional[str] = None
    demo_video_date: Optional[str] = None
    contract_timeline: Optional[str] = None
    checkin_schedule: Optional[str] = None
    action_items: list[str] = field(default_factory=list)


EXTRACTION_PROMPT = """You are extracting structured data from meeting notes for a course production call between Marian (from 21 Draw) and an artist.

Extract the following information from the meeting notes. If a field cannot be found, use null.

Return ONLY valid JSON with this exact structure (no markdown, no explanation):
{
  "artist_first_name": "string - first name only",
  "artist_email": "string - email address of the artist",
  "course_subject": "string - topic/subject of the course being produced",
  "outline_delivery_date": "string or null - when course outline should be delivered",
  "demo_video_date": "string or null - when demo videos are due",
  "contract_timeline": "string or null - start and end dates from contract",
  "checkin_schedule": "string or null - how often check-ins will happen",
  "action_items": ["array of strings - specific tasks/next steps mentioned"]
}

Important:
- For artist_email, look for email addresses mentioned in the notes, especially in attendee lists or contact information
- For action_items, include specific deliverables and deadlines mentioned
- Keep dates in their original format as mentioned in the notes
- If the artist email is not explicitly stated, look for it in the meeting participants or attendee list

Meeting notes to parse:
"""


class NotesParser:
    """Parse meeting notes using Claude AI."""

    def __init__(self, api_key: str):
        """
        Initialize the parser.

        Args:
            api_key: Anthropic API key
        """
        self.client = anthropic.Anthropic(api_key=api_key)

    def parse(self, notes_text: str, artist_name_hint: Optional[str] = None) -> MeetingData:
        """
        Parse meeting notes and extract structured data.

        Args:
            notes_text: Raw meeting notes text
            artist_name_hint: Optional artist name extracted from email subject

        Returns:
            MeetingData with extracted information
        """
        prompt = EXTRACTION_PROMPT + notes_text

        if artist_name_hint:
            prompt += f"\n\nNote: The artist name from the email subject is: {artist_name_hint}"

        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        # Extract JSON from response
        response_text = message.content[0].text.strip()

        # Try to parse JSON
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            data = json.loads(response_text)

        return MeetingData(
            artist_first_name=data.get("artist_first_name", artist_name_hint or ""),
            artist_email=data.get("artist_email", ""),
            course_subject=data.get("course_subject", ""),
            outline_delivery_date=data.get("outline_delivery_date"),
            demo_video_date=data.get("demo_video_date"),
            contract_timeline=data.get("contract_timeline"),
            checkin_schedule=data.get("checkin_schedule"),
            action_items=data.get("action_items", []),
        )
