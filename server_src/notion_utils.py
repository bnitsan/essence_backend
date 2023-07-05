import uuid
import os
from pprint import pprint
from notion_client import Client
import datetime
import re
import base64
import requests
import json

token = os.getenv("NOTION_KEY")
if not os.getenv("NOTION_KEY"):
    token = open("../Notion_integration_token.txt", "r").read()

client_id = os.getenv("NOTION_CLIENT_ID")
client_secret = os.getenv("NOTION_CLIENT_SECRET")
if not client_id or not client_secret:
    client_id = open("../Notion_client_id.txt", "r").read()
    client_secret = open("../Notion_client_secret.txt", "r").read()
    
def get_access_token(code):
    url = 'https://api.notion.com/v1/oauth/token'
        
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': 'https://essence.fyi/notionvalidate'
    }
    headers = {'Content-Type': 'application/json'}

    response = requests.post(url, json=data, headers=headers, auth=(client_id, client_secret))

    return response.json()


def extract_database_code(link):
    '''
    passed:
        assert extract_code("https://www.notion.so/593c94f0f6484ae5805f3867bd8c5fe6?v=0a26d60f65b74afea73fbc00d475072e") == "593c94f0f6484ae5805f3867bd8c5fe6"
        assert extract_code("https://notion.so/593c94f0f6484ae5805f3867bd8c5fe6") == "593c94f0f6484ae5805f3867bd8c5fe6"
        assert extract_code("notion.so/593c94f0f6484ae5805f3867bd8c5fe6?v=0a26d60f65b74afea73fbc00d475072e") == "593c94f0f6484ae5805f3867bd8c5fe6"
        assert extract_code("https://www.notion.so/") == None
        assert extract_code("https://www.notion.so/my-page-title-123") == "my-page-title-123"
        assert extract_code("https://notion.so/my-page-title-123") == "my-page-title-123"
        assert extract_code("my-page-title-123") == "my-page-title-123"
        assert extract_code("https://www.notion.so/native/593c94f0f6484ae5805f3867bd8c5fe6?v=0a26d60f65b74afea73fbc00d475072e&dee") == "593c94f0f6484ae5805f3867bd8c5fe6"
    '''
    if 'notion.so/native/' in link:
        link = link.replace('native/', '')
    regex = r"(?:https?://)?(?:www\.)?(?:notion\.so/)?([\w-]+)?(?:\?.*)?"
    match = re.search(regex, link)
    if match:
        return match.group(1)
    else:
        return None

def essence_session_to_notion(session):
    """Convert an Essence session to a notion session"""

    notion_session = {}
    notion_session["title"] = session["title"]
    notion_session["url"] = session["url"]
    
    notion_session["content"] = {}
    notion_session["content"]["qa_list"] = session["qa_list"]
    notion_session["content"]["palettes"] = session["long_summary"]
    
    notion_session["notion_fields"] = {}

    return notion_session

def get_icon_field(icon_field):
    """Get the icon field. SEMI-IMPLEMENTED"""

    return {"type": "emoji", "emoji": "🧵"}

def get_cover_field(cover_field):
    """Get the cover field. SEMI-IMPLEMENTED"""

    return {"type": "external", "external": {"url": "https://upload.wikimedia.org/wikipedia/commons/9/94/Starry_Night_Over_the_Rhone.jpg"}}

def add_notion_fields(page, database_id, notion_fields):
    """Add notion basic fields to a page"""

    page["parent"] = {"type": "database_id", "database_id": database_id}
    if "icon" in notion_fields: page["icon"] = get_icon_field(notion_fields["icon"])
    if "cover" in notion_fields: page["cover"] = get_cover_field(notion_fields["cover"])

    return page

def is_bulletpoint_list(output):
    for i in range(len(output)):
        if output[i]["key"] != i+1 or isinstance(output[i]["value"], list): return False

    return True

def rich_text_block(text, type="heading_2", url=None, bold=False, italic=False):
    if url is not None and url.startswith("file://"):
        url = None
    
    data = {
        "text": {
            "content": text
        },
        "annotations": {
            "bold": bold,
            "italic": italic,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": "default"
        }
    }

    if url is not None:
        data["text"]["link"] = {"url": url}
        data["href"] = url

    return [{
            "object": "block",
            type: {
                "rich_text": [
                    data
                ],
            }
        }]

def bulletpoint_single_block(text):
    return {
        "object": "block",
        "bulleted_list_item": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    },
                    "annotations": {
                        "bold": False,
                        "italic": False,
                        "strikethrough": False,
                        "underline": False,
                        "code": False,
                        "color": "default"
                    },
                    "plain_text": text,
                    "href": None
                }
            ]
        }
    }

def bulletpoints_block(list_to_add):
    if list_to_add is None or len(list_to_add) == 0: return []

    return [bulletpoint_single_block(bulletpoint) for bulletpoint in list_to_add]

def table_cell(text):
    return [
            {
                "type": "text",
                "text": {
                "content": text
                },
                "plain_text": text
            }
            ]

def table_row_cells(table_row):
    return [table_cell(cell) for cell in table_row]

def table_row(table_row):
    return {
        "type": "table_row",
        "table_row": {
        "cells": table_row_cells(table_row)
        }
    }

def table_block(table_to_add):
    return [{
        "type": "table",
        "table": {
            "table_width": len(table_to_add[0]),
            "has_column_header": True,
            "has_row_header": False,
            "children": [table_row(row) for row in table_to_add]
        }
        }]

def key_val_paragraph(key, value):
    return [
        {
        "object": "block",
        'paragraph': {'color': 'default',
                        'rich_text': [{'annotations': {'bold': True,
                                                    'code': False,
                                                    'color': 'default',
                                                    'italic': False,
                                                    'strikethrough': False,
                                                    'underline': False},
                                    'href': None,
                                    'plain_text': key,
                                    'text': {'content': key,
                                                'link': None},
                                    'type': 'text'},
                                    {'annotations': {'bold': False,
                                                    'code': False,
                                                    'color': 'default',
                                                    'italic': False,
                                                    'strikethrough': False,
                                                    'underline': False},
                                    'href': None,
                                    'plain_text': ' ' + value,
                                    'text': {'content': ' ' + value,
                                                'link': None},
                                    'type': 'text'}]},
    }]
    
def palette_content_block(output):
    """
        output is a list of {key: value} pairs.
        There are a few scenarios:
            1) key is None or '', value is a string: just add the string
            2) keys are successive integers: add a numbered list/bullet points
            3) keys are strings, values are strings: add as heading and text
            4) keys are strings, values are list of lists: add as heading and a table
    """
    if not output or len(output) == 0: return []

    # Case 1
    if len(output) == 1:
        if output[0]["key"] is None or output[0]["key"] == "":
            return rich_text_block(output[0]["value"], type="paragraph")
    
    # Case 2
    if is_bulletpoint_list(output):
        list_to_add = [out_i["value"] for out_i in output]

        return bulletpoints_block(list_to_add)
    
    # Case 3 + 4
    output_block = []
    for out_i in output:
        key, value = out_i["key"], out_i["value"]
        if isinstance(value, list):
            output_block.extend(rich_text_block(key, type="heading_3"))
            output_block.extend(table_block(value))
        else:
            output_block.extend(key_val_paragraph(key, value))
            # output_block.extend(rich_text_block(key, type="paragraph", bold=True))
            # output_block.extend(rich_text_block(value, type="paragraph"))

    return output_block

def get_palette_children(palettes):
    if palettes is None or len(palettes) == 0: return []

    palette_children = []

    for palette in palettes:
        palette_id = str(uuid.uuid4())
        palette_children.extend(rich_text_block(palette["title"], type="heading_3", url=palette["url"]))
        palette_children.extend(palette_content_block(palette["text"]))

    return palette_children

def get_qa_paragraph(question, answer):
    return [{
            "object": "block",
            "paragraph": {
                "rich_text": [
                    {'annotations': {'bold': True,
                                    'code': False,
                                    'color': 'default',
                                    'italic': False,
                                    'strikethrough': False,
                                    'underline': False},
                    'href': None,
                    'plain_text': question + '\n',
                    'text': {'content': question + '\n',
                            'link': None},
                    'type': 'text'},
                    {'annotations': {'bold': False,
                                    'code': False,
                                    'color': 'default',
                                    'italic': False,
                                    'strikethrough': False,
                                    'underline': False},
                    'href': None,
                    'plain_text': answer,
                    'text': {'content': answer,
                            'link': None},
                    'type': 'text'},
                ]
            }
        }]

def get_qa_children(qa_list):
    if qa_list is None or len(qa_list) == 0: return []

    qa_list_children = []

    qa_list_children.extend(rich_text_block("Questions and Answers", type="heading_2"))

    for qa in qa_list:
        qa_list_children.extend(get_qa_paragraph(qa[0], qa[1]))

    return qa_list_children

def get_page_children(content):
    children = []
    
    children.extend(get_palette_children(content["palettes"]))
    children.extend(get_qa_children(content["qa_list"]))

    return children

def get_properties_field(session):
    """
        Get the properties field
        Currently very non-generic.
        session as described in add_session(...)
    """

    properties = {}
    
    properties["Title"] = {
        "title": [
            {
                "text": {
                    "content": session["title"]
                }
            }
        ]
    }
    properties["Date Added"] = {
        "date": 
            {
                "start": datetime.datetime.now().strftime("%Y-%m-%d"),
                "end": None
            }
    }
    return properties

def create_new_page_from_session(session, database_id):
    """
    Add a session to the database
    - session: the session to add, JSON:
        {
            "notion_fields": {...}
            "title": "title",
            "content": {
                "palettes": [...],
                "qa_list": [...],
            }
        }
    - database_id: the database id, String
    
    """

    if "notion_fields" not in session: session["notion_fields"] = {}

    new_page = {}

    new_page = add_notion_fields(new_page, database_id, session["notion_fields"])
    
    new_page["properties"] = get_properties_field(session)

    new_page["children"] = get_page_children(session["content"])

    return new_page

def add_session(session, database_id, access_token):
    new_page_args = create_new_page_from_session(session, database_id)
    
    notion = Client(auth=access_token)

    try:
        created_page = notion.pages.create(**new_page_args)
    except Exception as e:
        print("Error creating page: ", e)
        return None

    return created_page