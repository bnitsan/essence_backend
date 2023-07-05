from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
import json

def extract_video_id(url):
    video_id = None
    url_parts = urlparse(url)
    if url_parts.hostname == "www.youtube.com" or url_parts.hostname == "youtube.com":
        if "/watch" in url_parts.path:
            query = parse_qs(url_parts.query)
            video_id = query["v"][0]
        elif "/embed/" in url_parts.path:
            video_id = url_parts.path.split("/")[-1]
    elif url_parts.hostname == "youtu.be":
        video_id = url_parts.path.lstrip("/")
    if video_id is not None and "&" in video_id:
        video_id = video_id.split("&")[0]
    return video_id

def combine_transcript_lines(transcript, time_tolerance=0.1):
    '''
    A heuristic to combine YouTube transcript lines into sentences.
    '''
    lines = []
    current_line = ""
    current_start = 0.0
    for i, line in enumerate(transcript):
        text = line["text"]
        start = line["start"]
        duration = line["duration"]
        if i == 0:
            current_line = text
            current_start = start
        else:
            prev_end = start - time_tolerance
            if start < current_start + duration and prev_end >= current_start:
                current_line += " " + text
            else:
                lines.append(current_line.strip() + ".")
                current_line = text
            current_start = start
    lines.append(current_line.strip() + ".")
    return "\n".join(lines)

def get_youtube_text(url):
    video_id = extract_video_id(url)
    if video_id is None:
        return '', ''
    
    try:
        yt_response = YouTubeTranscriptApi.get_transcript(video_id, languages=('en','en-GB'))
    except Exception as e:
        return '', ''

    combined_text = combine_transcript_lines(yt_response)

    return combined_text, json.dumps(yt_response)
