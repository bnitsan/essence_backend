import uuid
import re
import bcrypt
from urllib.parse import urlparse
import csv
import os
from typing import Type
from . import scraping_utils, gpt_utils, export_utils, nlp_utils, notion_utils
import json
import datetime
from sqlalchemy import and_
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import yaml

date_time_format = "%Y-%m-%d %H:%M:%S"
data_path = '/data'

max_number_users = 50
default_query_quota = 50
default_question_quota = 50

with open("server_src/config.yml", 'r') as ymlfile:
    cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)
    cfg = cfg["config"]

MAX_CHAR_LEN_QA = cfg["MAX_CHAR_LEN_QA"]
DEBUG_USERNAME = cfg["DEBUG_USERNAME"]

def init_server_utils(data_path_in, DBVariable, app, db):
    global data_path, max_number_users, default_query_quota, default_question_quota
    data_path = data_path_in

    with app.app_context():
        db_vars = DBVariable.query.all()
    for var in db_vars:
        try:
            if var.name == 'max_number_users':
                max_number_users = int(var.value)
            if var.name == 'default_query_quota':
                default_query_quota = int(var.value)
            if var.name == 'default_question_quota':
                default_question_quota = int(var.value)
        except:
            print('Error: could not convert to int')

def print_log(text, username=None, text_private=None):
    '''
        This is a custom printing function.
        If username is None, then it prints 'text' to the console and to the log file.
        If username is not None and is different than DEBUG_USERNAME, then it prints 'text_private' to the console and to the log file.
        If username is not None and is equal to DEBUG_USERNAME, then it prints 'text' to the console and to the log file.
    '''
    if username == None:
        print(text)
        with open(os.path.join(data_path, 'log.txt'), 'a') as f:
            f.write(text + '\n')

    if username != DEBUG_USERNAME:
        if text_private == None:
            return
        text = text_private
    print(text)
    with open(os.path.join(data_path, 'log.txt'), 'a') as f:
        f.writelines(text + '\n')

def get_allowed_emails():
    allowed_emails = []
    with open(os.path.join(data_path, 'allowed_emails.csv'), 'r') as f:
        for line in f:
            candidate = line.strip()
            if candidate and len(candidate) >= 5:
                allowed_emails.append(candidate)
    print('allowed_emails: ', allowed_emails)
    return allowed_emails

def embed_text(title, text):
    '''Not implemented yet.'''
    print('going to embed text of ' + title + '...')
    print('with text: ' + text)

def get_divider_of_user(user, divider_id, app, db, User):
    user = User.query.filter_by(name=user).first()
    if user is None:
        return None

    saved_dividers = user.saved_dividers
    saved_dividers = json.loads(saved_dividers)
    divider = None
    for divider_i in saved_dividers: # we are doing a linear search here, but it should be fine since the number of dividers is small; in the future consider sorting the dividers for example; or use a dict
        if divider_i['subject'] == divider_id: # we assume divider_i subject is unique and use it as id. Perhaps better to use id?
            divider = divider_i
            break
    if divider is None:
        return None

    return divider

def get_csv_of_session(url, title, output, qa_list, data_path):

    id = str(uuid.uuid4())
    path = os.path.join(data_path, 'export_csvs/'+id+'.csv')
    export_utils.export_session_to_csv(url, title, output, qa_list, path=path)

    return id

def get_csv_of_divider(user, divider_id, app, db, User, data_path):

    data = get_divider_of_user(user, divider_id, app, db, User)
    if data is None:
        return None

    id = str(uuid.uuid4())
    path = os.path.join(data_path, 'export_csvs/'+id+'.csv')
    export_utils.export_divider_to_csv(data, path=path)

    return id
    
def is_valid_url(url_candidate):
    '''
    Checks if s is a valid URL.
    Returns True/False.
    Can fail if URL is "semi-valid" (e.g. missing http://).
    
    Can add "schema" e.g. by
    if not re.match(r'^[a-zA-Z]+://', url_candidate):
        url_candidate = 'http://' + url_candidate
    '''
    return bool(urlparse(url_candidate).scheme)

def expired_date(date1, date2, days=1, hours=0, minutes=0):
    '''
    Checks if date1 is more than days days after date2.
    Returns True/False.
    '''
    delta = datetime.datetime.strptime(date1, date_time_format) - datetime.datetime.strptime(date2, date_time_format)
    return delta > datetime.timedelta(days=days, hours=hours, minutes=minutes)

def should_use_cached_data(message, db, app, UserQuery, user_id, days=50, hours=0, minutes=0):
    # searches in previous user queries. If previous query is found, 
    # is not older than X days, and is not marked as private or bad, 
    # it returns True and the cached data.
    # Otherwise, returns False and None.
    url = message['URL']
    date = message['date']
    style = message['style']

    # we do not support marked text caching for now, mostly as a security measure, also because it probably won't be used much due to variation in marked text
    if 'is_marked_text' in message and message['is_marked_text']:
        return False, None

    with app.app_context():
        # get user_query, filtered by url, style, private_flag and good_bad_flag of 0 or 1, sort by date
        user_query = UserQuery.query.filter(
            UserQuery.url == url,
            UserQuery.style_name == style,
            UserQuery.is_private == False,
            UserQuery.marked_text == '', # Currently not supporting marked_text. Since marked_text could be private information, we might only use it for a single user, therefore not a huge optimization gain.
            UserQuery.good_bad_flag.in_([0, 1])
        ).order_by(UserQuery.date.desc()).first()

        if user_query is not None and not expired_date(date, user_query.date, days=days, hours=hours, minutes=minutes):
            output = {
                'URL': url, 
                'style': style, 
                'output': user_query.model_output_parsed,
                'model_output': user_query.model_output,
                'original_web': user_query.original_web,
                'cleaned_text': user_query.cleaned_text,
                'from_cached_query': user_query.id,
                'title': user_query.title,
                'status': 'SUCCESS'}
            return True, output
        else:
            # look for private query from the same user.
            user_query = UserQuery.query.filter(
                UserQuery.url == url,
                UserQuery.style_name == style,
                UserQuery.is_private == True,
                UserQuery.user_id == user_id,
                UserQuery.marked_text == '', # Currently not supporting marked_text. Since marked_text could be private information, we might only use it for a single user, therefore not a huge optimization gain.
                UserQuery.good_bad_flag.in_([0, 1])
            ).order_by(UserQuery.date.desc()).first()
            if user_query is not None and not expired_date(date, user_query.date, days=days, hours=hours, minutes=minutes):
                output = {
                    'URL': url, 
                    'style': style, 
                    'output': user_query.model_output_parsed,
                    'model_output': user_query.model_output,
                    'original_web': user_query.original_web,
                    'cleaned_text': user_query.cleaned_text,
                    'from_cached_query': user_query.id,
                    'title': user_query.title,
                    'status': 'SUCCESS'}
                return True, output

            return False, None

def print_request_info(args):
    '''
    We assume args is a dictionary.
    '''
    print('---------------------------')
    print('Request arguments are:')
    for key, value in args.items():
        if isinstance(value, str):
            value_limited = value[:100]
        else:
            value_limited = str(value)[:100]
        print(key + ': ' + value_limited)

def is_email_valid(username):
    '''
    Checks if username is a valid email.
    Returns None if invalid, otherwise returns the regex result.
    '''
    regex = r"\"?([-a-zA-Z0-9._`?{}]+@[-a-zA-Z0-9._]+\.\w+)\"?" # should also allow addresses with '-' in them

    return re.match(regex, username)

def signup_user(username, password, app, db, User):
    with app.app_context():

        current_number_of_users = User.query.count()

        username = username.lower()

        if not is_email_valid(username):
            return {"success": False, "message": "Error: username must be an email"}

        # Here we can add a list of allowed emails, if we want to limit the users
        if False:
            if username not in get_allowed_emails():
                return {"success": False, "message": "Error: username not allowed"}

        user = User.query.filter_by(name=username).first()
        if user is not None:
            return {"success": False, "message": "Error: User already exists"}
        
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        db.session.add(
            User(
                id=str(uuid.uuid4()), 
                name=username, 
                email=username, 
                password=hashed_password,
                api_key="N/A",
                char_limit=100000,
                saved_dividers=json.dumps([]),
                last_query_date=datetime.datetime.now().astimezone().strftime(date_time_format),
                signup_date=datetime.datetime.now().astimezone().strftime(date_time_format),
                user_type="betatester",
                remaining_queries=0 if current_number_of_users > max_number_users else default_query_quota,
                remaining_questions=0 if current_number_of_users > max_number_users else default_question_quota,
                )
        )
        db.session.commit()
    if current_number_of_users > max_number_users:
        return {"success": True, "message": "User created successfully, but without compute quota. We will let you know when you can start using the service. Sorry for the inconvenience."}
    return {"success": True, "message": "User created successfully"}

def login_user(username, password, app, db, User):
    username = username.lower()

    with app.app_context():
        
        user = User.query.filter_by(name=username).first()
        if user is not None:
            enc_password = password.encode('utf-8')

            try:
                if not bcrypt.checkpw(enc_password, user.password):
                    return {"success": False, "message": "Error: Incorrect credentials"}
                else:
                    print_log(username + " logged in successfully.", username, text_private=username + " logged in successfully.")
            except Exception as e:
                # this is mainly to counteract the "ValueError: Invalid hashed_password salt" that occurs when switching between dev server and prod server
                print_log(str(e), username, text_private=str(e))
                return {"success": False, "message": "Error: try resetting your password via the forgot password link."}
        else:
            return {"success": False, "message": "Error: Incorrect credentials"}

    return {"success": True, "message": "User logged-in successfully", "JWT": "N/A"}

def save_feedback(field1: str, field2: str) -> None:
    global data_path
    with open(os.path.join(data_path, 'feedback.csv'), 'a', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([field1, field2])

def save_email_to_waiting_list(data_path: str, list_name: str, email: str) -> None:
    path = os.path.join(data_path, 'waiting_list.csv')
    # Initialize empty csv file is path does not exist
    if not os.path.exists(path):
        with open(path, 'w', newline='') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(['email', 'list_name', 'date'])

    with open(path, 'a', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([email, list_name, datetime.datetime.now()])

def get_answer_on_url(question, url, marked_text, web_html, qa_list, data_path, username, min_marked_length=100):
    if marked_text and len(marked_text) > min_marked_length:
        marked_text = nlp_utils.clean_marked_text(marked_text)
        text = marked_text
        original_text = marked_text
    elif len(web_html) > 0:
        print_log("Using web html... " + web_html[:150], username, text_private="Using web html... ")
        text, original_text = scraping_utils.html_to_text(web_html)
    else:
        text, original_text = scraping_utils.url_to_text(url, data_path)
    
    if text == '':
        return "Error in getting text from the page. Try marking text (possibly all of it).", {}, "No source."
    
    answer, model_prompt, supporting_quote = gpt_utils.qa_about_text(question, text[:MAX_CHAR_LEN_QA], url, qa_list)
    if answer.startswith("ERROR"):
        return answer, {}, ""
    if len(text) > MAX_CHAR_LEN_QA:
        answer += " (Note: the answer is based on the first {} characters of the page.)".format(MAX_CHAR_LEN_QA)

    backend_answer = {"original_web": original_text, "cleaned_web": text, "model_prompt": model_prompt, "marked_text": marked_text}

    return answer, backend_answer, supporting_quote

def get_answer_on_chat(question, qa_list, data_path, username):
    if question.startswith("/chat"):
        question = question[5:].strip()
    answer = gpt_utils.chat_question(question, qa_list)
    backend_answer = {'success': True} if len(answer) > 0 else {}

    return answer, backend_answer

def save_session(data, divider_name, username, app, db, User):
    print_log("Saving session... with data: " + str(data)[:150], username, text_private="Saving session...")
    with app.app_context():
        user = User.query.filter_by(name=username).first()

        user_saved_dividers = json.loads(user.saved_dividers)
        for saved_divider in user_saved_dividers:
            if saved_divider["subject"] == divider_name:
                saved_divider["content"].append({
                    'id': str(uuid.uuid4()), 
                    'title': data['title'],
                    'url': data['url'],
                    'long_summary': data['long_summary'],
                    'qa_list': data['qa_list'] if 'qa_list' in data else [],})

                user.saved_dividers = json.dumps(user_saved_dividers)
                db.session.commit()
                return {"Success": "Saved session."}
    return {"Error": "Divider not found. Please create a new divider first."}

def delete_session(subject, session_id, username, app, db, User):
    with app.app_context():
        user = User.query.filter_by(name=username).first()
        user_saved_dividers = json.loads(user.saved_dividers)
        print_log('Trying to delete id: ' + session_id + ' from subject: ' + subject, username, text_private=None)
        for saved_divider in user_saved_dividers:
            if saved_divider["subject"] == subject:
                for session in saved_divider["content"]:
                    if session["id"] == session_id:
                        saved_divider["content"].remove(session)
                        user.saved_dividers = json.dumps(user_saved_dividers)
                        db.session.commit()
                        return {"Success": "Deleted session."}
    return {"Error": "Did not find session."}

def add_divider(divider_name, username, app, db, User):
    with app.app_context():
        user = User.query.filter_by(name=username).first()

        saved_queries_json = json.loads(user.saved_dividers)
        print_log('user_saved_dividers: ' + str(saved_queries_json)[:150], username, text_private=None)

        for saved_divider in saved_queries_json:
            print_log('Saved divider: ' + str(saved_divider)[:150], username, text_private=None)
            if saved_divider["subject"] == divider_name:
                return {"Error": "Divider already exists."}

        saved_queries_json.append({"key": 0, "subject": divider_name, "content": []})
        
        user.saved_dividers = json.dumps(saved_queries_json)
        db.session.commit()

        user = User.query.filter_by(name=username).first()
        
        print_log('Saved dividers: ' + str(user.saved_dividers)[:150], username, text_private='Saved dividers to user ' + username)

    return {"Success": "Added divider."}

def delete_divider(divider_name, username, app, db, User):
    with app.app_context():
        user = User.query.filter_by(name=username).first()
        
        saved_dividers = json.loads(user.saved_dividers)

        for saved_divider in saved_dividers:
            if saved_divider["subject"] == divider_name:
                saved_dividers.remove(saved_divider)
                user.saved_dividers = json.dumps(saved_dividers)
                db.session.commit()
                return {"Success": "Deleted divider."}
    return {"Error": "Did not find divider."}

def get_styles(app, db, Style):
    with app.app_context():
        styles = Style.query.all()
        styles = [style.name for style in styles]
    return styles

def get_saved_data(username, app, db, User):
    with app.app_context():
        user = User.query.filter_by(name=username).first()
        if not user:
            return []
        saved_dividers = json.loads(user.saved_dividers)
    return saved_dividers

def enough_input_params(args, required_params):
    '''
    Checks if args has all the required parameters.
    Returns True/False.
    '''
    for param in required_params:
        if param not in args:
            return False
    return True

def processed_tweet_exists(tweetid, app, db, UserQuery, style):
    '''
    Checks if the tweet has already been processed.
    Returns True/False.
    '''
    with app.app_context():
        user_query = UserQuery.query.filter(UserQuery.url.like('%twitter.com%'), 
                                            UserQuery.url.like('%' + tweetid + '%'),
                                            UserQuery.style_name == style,
                                            UserQuery.is_private == False,
                                            UserQuery.marked_text == '', 
                                            UserQuery.good_bad_flag.in_([0, 1])
                                            ).order_by(UserQuery.date.desc()).first()
        if user_query:
            return user_query.model_output_parsed
        else:
            return None

def print_object(obj):
    '''
    Prints the object in a readable format.
    '''
    print(obj)

def get_auto_title(subtitles):
    '''
    Returns a unified title given several subtitles
    '''
    eligible_subtitles = []
    for subtitle in subtitles:
        if (subtitle is not None) and subtitle != '' and subtitle != 'Note':
            eligible_subtitles.append(subtitle)

    if len(eligible_subtitles) == 0:
        return ''
    elif len(eligible_subtitles) == 1:
        return eligible_subtitles[0]
    else:
        joined_titles = 'Subtitle: ' + '\nSubtitle: '.join(eligible_subtitles)
        title = gpt_utils.get_title_for_entry('', query_to_model = "Summarize the following subtitles to something that can serve as an overall title.\nSubtitles:\n" + joined_titles + "\nTitle:")
        return title

def send_email(user_emails, subject, text):
    '''
    Sends an email to the user. Uses SendGrid.
    Can send to multiple users by passing a list of emails.
    '''

    message = Mail(
        from_email='support@essence.fyi',
        to_emails=user_emails,
        subject=subject,
        html_content=text)
    try:
        sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
        response = sg.send(message)
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(e.message)

def send_password_reset_link(username, app, db, User):
    with app.app_context():
        user = User.query.filter_by(name=username).first()
        if user:
            # generate a random token
            token = str(uuid.uuid4())

            # save the token to the db
            user.forgot_pw_token = token
            db.session.commit()

            # send an email to the user with the link
            message = 'Hi ' + username + ',<br><br>Click the link below to reset your password:<br><br><a href="https://essence.fyi/resetpassword?username=' + username + '&token=' + token + '">https://essence.fyi/resetpassword?username=' + username + '&token=' + token + '</a><br><br>Thanks,<br>Team Essence'

            send_email(user.email, 'Essence password Reset Link', message)
            return {"Success": "Sent password reset link."}
    print('User not found or error occured in sending password-reset email.')        
    return {"Error": "User not found."}

def set_new_password(username, token, new_password, app, db, User):
    # look for user in db
    with app.app_context():
        user = User.query.filter_by(name=username).first()
        if user:
            # check if token matches
            if user.forgot_pw_token == token:
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
                user.password = hashed_password
                user.forgot_pw_token = None
                db.session.commit()
                print('Successsfully reset password.')
                return {"Success": "Password reset."}
            else:
                return {"Error": "Token does not match."}
        
    return {"Error": "User not found."}

def user_has_credits(app, user, type='process'):
    if type != 'process' and type != 'question':
        return False
    print('Checking if user has credits... Remaining queries: ' + str(user.remaining_queries) + ', Remaining questions: ' + str(user.remaining_questions))
    with app.app_context():
        if type == 'process':
            if user.remaining_queries > 0:
                return True
        elif type == 'question':
            if user.remaining_questions > 0:
                return True
    return False
    
def update_user_quota(username, new_queries, new_questions, code, app, db, User):
    if code != os.getenv('UPDATE_QUOTA_CODE'):
        return {"Error": "Invalid API key."}
    
    try:
        new_queries = int(new_queries)
        new_questions = int(new_questions)
    except:
        return {"Error": "Invalid input."}

    if new_queries < 0 or new_questions < 0 or new_queries > 100 or new_questions > 100:
        return {"Error": "Invalid input."}
    
    with app.app_context():
        user = User.query.filter_by(name=username).first()
        if user:
            user.remaining_queries = new_queries
            user.remaining_questions = new_questions
            db.session.commit()
            return {"Success": "Quota updated."}
    
    return {"Error": "Error occured."}

def update_allowed_number_of_users(new_allowed_users, app, db, User, DBVariable):
    count_new_active = 0
    with app.app_context():
        var = DBVariable.query.filter_by(name='max_number_users').first()
        if var:
            print('Updating to value: ' + str(new_allowed_users))
            var.value = new_allowed_users
            db.session.commit()

        # update quotas for first registered 100 users with 0 remaining queries or 0 remaining questions.
        users = User.query.order_by(User.signup_date).limit(max_number_users).all()
        print('Users: ' + str(users))
        for user in users:
            if user.remaining_queries == 0 and user.remaining_questions == 0:
                print('Found one: ' + user.name)
                user.remaining_queries = default_query_quota
                user.remaining_questions = default_question_quota

                count_new_active += 1

        db.session.commit()

    return {"Success_new_users": "Updated allowed number of users. " + str(count_new_active) + " users were given new credits."}
            
def generate_notion_token_id(username, app, db, User, NotionRequest):
    with app.app_context():
        user = User.query.filter_by(name=username).first()
        if user:
            new_id = str(uuid.uuid4())
    
            db.session.add(
                NotionRequest(
                    id=new_id,
                    status='pending',
                    date=datetime.datetime.now().astimezone().strftime(date_time_format),
                    user_id=user.id
                    )
                )
            db.session.commit()
            return new_id

    return ''

def validate_notion(code, req_id, app, User, NotionRequest, db):
    access_token_response = notion_utils.get_access_token(code)

    with app.app_context():
        req = NotionRequest.query.filter_by(id=req_id).first()
        if req:
            req.status = 'success'
        else:
            return {"error": "No request found."}
        
        user = User.query.filter_by(id=req.user_id).first()
        if user:
            user.notion_access_token = access_token_response['access_token']
        
        db.session.commit()

    return {"success": "Successfully connected to Notion."}

def export_to_notion(session, database_id, username, User, NotionRequest, app):
    '''
    Exports the output to Notion.
    '''
    with app.app_context():
        user = User.query.filter_by(name=username).first()
        if user and len(user.notion_access_token) > 0:
            access_token = user.notion_access_token
        else:
            return {"error": "No Notion access token found. Try resetting your Notion access token."}

    content = {
        'url': session['url'],
        'title': session['title'],
        'long_summary': session['palettes'],
        'qa_list': session['qa_list'],
    }
    to_notion_session = notion_utils.essence_session_to_notion(content)
    
    database_id = notion_utils.extract_database_code(database_id)

    page = notion_utils.add_session(to_notion_session, database_id, access_token)

    if page is None:
        return {"error": "Error adding session to Notion."}
    
    return {"success": "Session added to Notion.", "error": False}

def handle_web_html(args):
    if "web_html" not in args:
        return ''

    web_html = args['web_html']
    if type(web_html) == tuple and type(web_html[0]) == str:
        return web_html[0]
    if type(web_html) == str:
        return web_html
    return ''

def get_remaining_queries_and_questions(username, app, db, User):
    with app.app_context():
        user = User.query.filter_by(name=username).first()
        if user:
            return {"remaining_queries": str(user.remaining_queries), "remaining_questions": str(user.remaining_questions)}
    return {"remaining_queries": "Unknown", "remaining_questions": "Unknown"}