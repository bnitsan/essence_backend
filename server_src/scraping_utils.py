import urllib.request
from urllib.parse import urlparse
import requests, justext, trafilatura
import uuid
import textract
import os
from . import twitter_utils, scihub_utils, youtube_utils
from cachelib.file import FileSystemCache
import yaml
import re
from pathlib import Path

with open("server_src/config.yml", 'r') as ymlfile:
    cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)
    cfg = cfg["config"]

CACHE_URL_SECONDS = cfg["CACHE_URL_SECONDS"]
CACHE_URL_THRESHOLD = cfg["CACHE_URL_THRESHOLD"]
MIN_SCRAPING_LENGTH = cfg["MIN_SCRAPING_LENGTH"]
MIN_SCRAPING_LENGTH_JS = cfg["MIN_SCRAPING_LENGTH_JS"]

data_path = os.path.abspath(os.path.join(str(Path(os.getcwd()).parent), 'data'))  # get absolute path to one folder up
if os.getenv("ESSENCE_DATA_PATH"):
    data_path = os.getenv("ESSENCE_DATA_PATH")
url_cache = FileSystemCache(os.path.join(data_path, 'url_cache') , threshold=CACHE_URL_THRESHOLD, default_timeout=CACHE_URL_SECONDS)

def url_to_text(url: str, data_path: str) -> str:
    '''
        Takes a URL and data path, checks the cache, and returns the text from the URL.
        Output: (text, original_text)
    '''
    print('URL is: ' + url)
    if url.startswith('file://'):
        return '', ''
    if url_cache.has(url):
        print('Using cached URL...')
        elem = url_cache.get(url)
        return elem['text'], elem['original_text']
    else:
        print('Fresh URL fetch...')
        text, original_text = url_to_text_mine(url, data_path)
        elem = {'text': text, 'original_text': original_text}
        if text != '':
            url_cache.set(url, elem)
        return text, original_text

def get_domain_name(url):
    domain = urlparse(url).netloc
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain

def bot_complying_url(url):
    '''
    A function to make sure the URL is not problematic for bots. Currently limited to handful of websites.
    '''
    domain = get_domain_name(url)
    if domain == 'arxiv.org':
        url = url.replace('www.arxiv.org', 'export.arxiv.org')
        url = url.replace('arxiv.org', 'export.arxiv.org')
    return url

def url_to_text_mine(url, data_path):
    '''
    Mines the url for text. Returns the "cleaned" text and the original text (e.g. HTML for websites).
    Does some special handling for particular sites
    '''
    domain = get_domain_name(url)
    if 'twitter.com' in domain:
        tweet = twitter_utils.detect_tweet(url)
        if tweet:
            try:           
                tweet, replies = twitter_utils.get_thread(tweet)
                replies_list = [tweet.data['text']] + [tweet.text for tweet in replies.data[::-1]]
                return '(The following is mined from Twitter and may contain garbage)\n' + '\n'.join(replies_list), '\n\n'.join(replies_list)
            except Exception as e:
                print(e)
                print('Error with Twitter API')
    if 'sci-hub' in domain:
        return pdf_to_text(url, data_path, special_getter=scihub_utils.get_pdf_bytes)
    if 'onlinelibrary.wiley.com' in domain and 'epdf' in url:
        url = url.replace('epdf', 'pdfdirect')
    if 'youtube.com' in domain or 'youtu.be' in domain:
        return youtube_utils.get_youtube_text(url)
    '''
    Get the website using requests
    '''
    url = bot_complying_url(url)
    try:
        response = requests.get(url, timeout=2)
        print(response.text[:100] + '...')
    except Exception as e:
        print("Timeout with requests (url_to_text): ")
        print(e)
        return ('', '')
    
    content_type = response.headers.get('content-type')

    if 'application/pdf' in content_type:
        ext = '.pdf'
        return pdf_to_text(url, data_path, response=response)
    elif 'text/html' in content_type:
        ext = '.html'
        return html_url_to_text(url, response=response)
    else:
        ext = ''
        print('Unknown type: {}'.format(content_type))
        return ('', '')

def pdf_to_text(url, data_path, response=None, special_getter=None):
    '''
    A function to convert a PDF URL to text.
    '''
    original_url_text = ''

    if not special_getter:
        try:
            if response is None:
                response = requests.get(url, timeout=2)
            pdf_content = response.content
        except:
            print("Timeout with requests")
            return ('', original_url_text)
    else:
        try:
            pdf_content = special_getter(url)
        except:
            print("Problem with special getter")
            return ('', original_url_text)

    if not os.path.exists(os.path.join(data_path, 'temp')): os.makedirs(os.path.join(data_path, 'temp'))
    temp_filename = os.path.join(data_path, 'temp/' + str(uuid.uuid4()) + '.pdf')
    with open(temp_filename, 'wb') as f:
        f.write(pdf_content)

    pdf_bytes = textract.process(temp_filename)

    text = bytes_to_string(pdf_bytes)
    clean_text = clean_pdf_text(text)

    print('clean_text: ' + clean_text[:100] + '...')
    return (clean_text, text)

def html_quality_check(text):
    '''
    A function to check if the HTML text is "good enough" to be used.
    '''
    JS_warnings = ['JavaScript is not available', 'you have been blocked', 'Cloudflare Ray ID', 'the archived page without enabling Javascript', 'Please enable JS and disable any ad blocker']

    if not text:
        return False
    
    if len(text) < MIN_SCRAPING_LENGTH:
        return False
        
    if len(text) < MIN_SCRAPING_LENGTH_JS and any(warning in text for warning in JS_warnings):
        return False
    
    if text.startswith('JavaScript is not available'):
        return False
    
    return True

def html_to_text(original_url_text, backend='trafilatura', attempt=0):
    '''
    A function to convert a URL to "clean" text. We use external libraries to do the initial clean.
    url (str): the URL to convert
    backend (str): We currently support two backends: 'justext' and 'trafilatura'.
    attempt (int): keeps track of how many times we tried to get the text from the URL, 
                    switching backends in the process.

    Returns:
        text (str): the text from the URL after cleaning (using the backend)
        original_url_text (str): the text from the URL before cleaning
    '''

    ######### justext #########
    if backend == 'justext':
        paragraphs = justext.justext(original_url_text, justext.get_stoplist("English"))
        text = ''
        for paragraph in paragraphs:
            if not paragraph.is_boilerplate:
                text += paragraph.text + '\n'
            else:
                pass
    
    ######### trafilatura #########
    elif backend == 'trafilatura':
        print('original url text with trafilatura: ' + original_url_text[:100] + '...')
        try:
            text = trafilatura.extract(original_url_text)
        except:
            print("Error occured with trafilatura extract.")
            text = ''
        
    ######### unsupported #########
    else:
        raise ValueError('Backend not supported')

    '''
    add first postprocessing on text: if the backend failed, try again with the other backend.
    Keep track of the number of attempts to avoid infinite loops. Stops at 2 attempts.
    '''
    if text == '' and attempt == 0:
        if backend == 'justext':
            print('trying again with trafilatura')
            text, original_url_text = html_to_text(original_url_text, 'trafilatura', attempt=1)
        elif backend == 'trafilatura':
            print('trying again with jusText')
            text, original_url_text = html_to_text(original_url_text, 'justext', attempt=1)

    ''' 
    Second postprocessing on text: none yet
    '''
    return (text, original_url_text) if (text and html_quality_check(text)) else ('', original_url_text)

def html_url_to_text(url, response=None, backend='trafilatura', attempt=0):
    '''
    A function to convert a URL to "clean" text. We use external libraries to do the initial clean.
    url (str): the URL to convert
    backend (str): We currently support two backends: 'justext' and 'trafilatura'.
    attempt (int): keeps track of how many times we tried to get the text from the URL, 
                    switching backends in the process.

    Returns:
        text (str): the text from the URL after cleaning (using the backend)
        original_url_text (str): the text from the URL before cleaning

    Comments: See https://adrien.barbaresi.eu/blog/evaluating-text-extraction-python.html
              for a claim that trafilatura is better than most alternatives.
    '''
    original_url_text = ''

    ######### justext #########
    if backend == 'justext':
        try:
            if response is None:
                response = requests.get(url, timeout=2)
            original_url_text = response.content
        except:
            print("Timeout with requests")
            return ('', original_url_text)
        paragraphs = justext.justext(response.content, justext.get_stoplist("English"))
        text = ''
        for paragraph in paragraphs:
            if not paragraph.is_boilerplate:
                text += paragraph.text + '\n'
            else:
                pass
    
    ######### trafilatura #########
    elif backend == 'trafilatura':
        try:
            downloaded = trafilatura.fetch_url(url)
            original_url_text = downloaded
            text = trafilatura.extract(downloaded)
        except:
            print("Timeout with trafilatura fetch_url")
            if attempt == 0:
                return html_url_to_text(url, backend='justext', attempt=1)
            return ('', original_url_text)
    
    ######### unsupported #########
    else:
        raise ValueError('Backend not supported')

    '''
    add first postprocessing on text: if the backend failed, try again with the other backend.
    Keep track of the number of attempts to avoid infinite loops. Stops at 2 attempts.
    '''
    if text == '' and attempt == 0:
        if backend == 'justext':
            print('trying again with trafilatura')
            text, original_url_text = html_url_to_text(url, 'trafilatura', attempt=1)
        elif backend == 'trafilatura':
            print('trying again with jusText')
            text, original_url_text = html_url_to_text(url, 'justext', attempt=1)

    ''' 
    Second postprocessing on text: none yet
    '''

    return (text, original_url_text) if (text and html_quality_check(text)) else ('', original_url_text)

def bytes_to_string(bytes):
    ''' 
    a function to convert bytes to string. 
    Currently simply uses decode() method with utf-8 encoding.
    '''
    return bytes.decode("utf-8")

def clean_pdf_text(text):
    '''
    A function to clean text extracted from PDFs.
    
    After noticing a problem in a paper that contained a lot of formulas that were parsed 
    as single-character-lines, we set for now one rule: remove lines with less than 10 characters.
    We also remove all consecutive spaces.
    '''
    text = ' '.join([line for line in text.split('\n') if len(line) >=10])
    # whereever there are more than 2 consecutive spaces, replace with 1 space
    text = re.sub(' +', ' ', text)
    return text

