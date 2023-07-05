import tweepy
import os
from pathlib import Path
import re
import timeout_decorator

bearer_token = os.getenv("TWITTER_BEARER_TOKEN")

if not bearer_token:
    path_here = os.getcwd()
    path = Path(path_here)
    with open(str(path.parent.absolute())+'/TwitterKeys.txt') as key_f:
        for line in key_f:
            if line.startswith('BearerToken'):
                bearer_token = line.split('=')[1].strip()
                break

client = tweepy.Client(bearer_token=bearer_token)

@timeout_decorator.timeout(3)
def get_tweet(tweet_id):
    tweet = client.get_tweet(tweet_id, tweet_fields=['author_id','entities','conversation_id','created_at'], user_fields=['name'], expansions=['author_id'])
    return tweet

@timeout_decorator.timeout(3)
def get_tweet_replies(tweet_ID, author_id):
    query = f"conversation_id:{tweet_ID} is:reply from:{author_id}"
    replies= client.search_recent_tweets(query=query, max_results=100)
    return replies

def get_thread(tweet_id):
    for i in range(3):
        try:
            tweet = get_tweet(tweet_id)
            break
        except timeout_decorator.timeout_decorator.TimeoutError:
            if i == 2:
                raise "Twitter API timeout."
    for i in range(3):
        try:
            replies = get_tweet_replies(tweet.data['id'], tweet.includes['users'][0].id)
            break
        except timeout_decorator.timeout_decorator.TimeoutError:
            if i == 2:
                raise "Twitter API timeout."
    return tweet, replies

def detect_tweet(url):
    # provisional way to detect if url is a tweet. If not, returns False, if yes, returns tweet ID
    if not(url.startswith('https://twitter.com/') or url.startswith('https://mobile.twitter.com/') or url.startswith('https://t.co/')):
        return False

    try:
        rest_of_url = url.split('/status/')[1]
    except IndexError:
        return False
    tweet_id = re.findall(r'\d+', rest_of_url)[0]  # get leading number of rest_of_url

    if len(tweet_id) > 15:
        return tweet_id
    else: return False