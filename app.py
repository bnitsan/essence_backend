"""
Written By Nitsan Bar

Flask-based development server for Essence extension.

We try to keep this file relatively clean, referring often to /src folder, especially server_utils.py 

"""

from flask import Flask, request, jsonify, make_response, render_template, redirect
from flask_cors import CORS, cross_origin
from server_src import gpt_utils, server_utils
import datetime
import uuid
from server_src.setup_db import User, UserQuery, Style, UserQuestion, NotionRequest, DBVariable, db
import time
import os
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, JWTManager, verify_jwt_in_request, get_jwt
import yaml
from threading import Thread
from flask_migrate import Migrate
from cachelib.file import FileSystemCache

with open("server_src/config.yml", 'r') as ymlfile:
    cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)
    cfg = cfg["config"]

debug_flag = True
if os.getenv("DEBUG_FLAG") == "False":
    debug_flag = False

app = Flask(__name__)
cors = CORS(app)
# app.config['CORS_HEADERS'] = 'Content-Type'

data_path = os.path.abspath(os.path.join(os.getcwd(), os.pardir, 'data'))  # get absolute path to one folder up
if os.getenv("ESSENCE_DATA_PATH"):
    data_path = os.getenv("ESSENCE_DATA_PATH")

db_path = os.path.join(data_path, "database.db")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///'+db_path
app.config['JSON_SORT_KEYS'] = False
db.init_app(app)

# allow for DB migrations and creation of new tables
migrate = Migrate(app, db)
with app.app_context():
    db.create_all()

server_utils.init_server_utils(data_path, DBVariable, app, db)

# JWT setup
ACCESS_EXPIRES = datetime.timedelta(days=364)
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = ACCESS_EXPIRES
app.config["JWT_SECRET_KEY"] = "essential_secret"
jwt = JWTManager(app)
jwt_cache_blocklist = FileSystemCache(os.path.join(data_path, 'jwt_blacklist') , threshold=10000, default_timeout=int(ACCESS_EXPIRES.total_seconds())) # redis.StrictRedis(host="localhost", port=6379, db=0, decode_responses=True)

@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload: dict):
    jti = jwt_payload["jti"]
    token_in_cache = jwt_cache_blocklist.get(jti)
    return token_in_cache is not None


########################
########################
###### WEB ROUTES ######
########################
########################

@app.route('/')
def home():
    server_utils.print_log('HOME page initiated! ' + str(datetime.datetime.now()))
    return render_template('index.html', message=None)

@app.route("/robots.txt")
def robots_dot_txt():
    server_utils.print_log('ROBOTS initiated! ' + str(datetime.datetime.now()))
    return "User-agent: *\Disallow: /requestaccess"

@app.route("/privacy")
def privacy():
    server_utils.print_log('PRIVACY initiated! ' + str(datetime.datetime.now()))
    return render_template('privacy.html', message=None)

@app.route("/termsofservice")
def termsofservice():
    server_utils.print_log('TERMS OF SERVICE initiated! ' + str(datetime.datetime.now()))
    return render_template('termsofservice.html', message=None)

@app.route('/travel', methods=['GET'])
def travel():
    server_utils.print_log('TRAVEL initiated! ' + str(datetime.datetime.now()))
    return render_template('travel.html', message=None)

@app.route('/spaper', methods=['GET'])
def spaper():
    server_utils.print_log('SPAPER initiated! ' + str(datetime.datetime.now()))
    # return render_template('spaper.html', message=None)
    return render_template('index.html', message=None)

@app.route('/biz', methods=['GET'])
def biz():
    server_utils.print_log('BIZ initiated! ' + str(datetime.datetime.now()))
    return render_template('biz.html', message=None)

@app.route("/tweet", methods=['GET'])
def tweet():
    server_utils.print_log('TWEET initiated! ' + str(datetime.datetime.now()))

    if not server_utils.enough_input_params(request.args, ["tweetid"]):
        return render_template('index.html', message=None)

    tweetid = request.args.get('tweetid')
    if tweetid is not None:
        server_utils.print_log('Tweet ID: ' + request.args.get('tweetid'))
        processed_tweet = server_utils.processed_tweet_exists(tweetid, app, db, UserQuery, 'bulletsgeneric')
        if processed_tweet is not None:
            message_list = [processed_tweet_i['value'] for processed_tweet_i in processed_tweet]
            return render_template('tweet.html', tweetUrl='https://twitter.com/x/status/' + tweetid, message=message_list)
        
    return render_template('tweet.html', tweetUrl='https://twitter.com/x/status/' + tweetid, message=['Sorry, tweet summary not available.'])

@app.route('/resetpassword', methods=['GET'])
def resetpassword():
    '''
        This method resets the password of the input user.
    '''
    server_utils.print_log('RESETPASSWORD initiated! ' + str(datetime.datetime.now()))
    args = request.args
    print(args)
    if not server_utils.enough_input_params(args, ["username", "token"]):
        return cfg["ERROR_NOT_ENOUGH_PARAMS"]

    return render_template('resetpassword.html', username=args["username"], token=args["token"])

@app.route('/chrome')
def chrome():
    server_utils.print_log('CHROME initiated! ' + str(datetime.datetime.now()))
    return redirect('https://chrome.google.com/webstore/detail/essence/agokfbniiemgojbmdbhijmhfppgeaeal')

@app.route('/notion')
def notion():
    server_utils.print_log('NOTION initiated! ' + str(datetime.datetime.now()))
    return redirect('https://helix-walnut-885.notion.site/Guide-to-joining-Essence-Notion-integration-fac472e69b094902a6cbae86075ef0e4')

@app.route('/notionvalidate')
def notionvalidate():
    server_utils.print_log('NOTIONVALIDATE initiated! ' + str(datetime.datetime.now()))
    
    args = request.args
    server_utils.print_log('args are: ' + str(args))
    if not server_utils.enough_input_params(args, ["code", "state"]):
        return {"Error": "Notion integration has not completed successfully."}
    
    code = args.get('code')
    req_id = args.get('state')

    response = server_utils.validate_notion(code, req_id, app, User, NotionRequest, db)
    
    if "error" in response:
        return render_template('index.html', message=response["error"])
    else:
        return redirect('https://helix-walnut-885.notion.site/5e5f3839de9b46a19785f93c23892d2c?v=d8a890babd5f40bfa371ed1d2e11c3a4')


########################
########################
###### API ROUTES ######
########################
########################

@app.route('/process', methods=['POST'])
@jwt_required()
def process():
    '''
    This is the main API route for the server, processing a URL into a structured output.
    An important principle is that the server does not reveal all query data to the user, but only the essential output.
    Therefore, we split the processing output to 1) output and 2) backend_output.
    '''

    server_utils.print_log('PROCESS initiated! ' + str(datetime.datetime.now()))

    args = request.get_json()
    
    if not server_utils.enough_input_params(args, ["url"]):
        return cfg["ERROR_NOT_ENOUGH_PARAMS"]

    server_utils.print_request_info(args)
    
    username = get_jwt_identity().lower()
    user = User.query.filter_by(name=username).first()
    user_id = user.id
    
    if not server_utils.user_has_credits(app, user, type='process'):
        return {"output": "Out of compute quota."}

    current_datetime = datetime.datetime.now().astimezone().strftime(server_utils.date_time_format)
    time_diff = (datetime.datetime.strptime(current_datetime, server_utils.date_time_format) - datetime.datetime.strptime(user.last_query_date, server_utils.date_time_format)).total_seconds()
    if time_diff < cfg["TIME_DIFF_USER_REQ_SEC"]:
        return {"output": "Please wait " + str(cfg["TIME_DIFF_USER_REQ_SEC"] - time_diff) + " seconds before sending another request."}
    user.last_query_date = current_datetime
    db.session.commit()

    message = {
        "URL": args["url"],
        "date": datetime.datetime.now().astimezone().strftime(server_utils.date_time_format), 
        "style": args["style"] if "style" in args else "",
        "sub_category": args["sub_category"] if "sub_category" in args else "",
        "req_id": args["req_id"] if "req_id" in args else '',
        "web_html": args["web_html"] if "web_html" in args else "",
    }

    should_use_cache, output = server_utils.should_use_cached_data(message, db, app, UserQuery, user_id)
    if should_use_cache:
        server_utils.print_log("Using cached data...", username, "Using cached data...")
        output['gpt_credits'] = 0
    else:
        server_utils.print_log("Not using cached data, fresh processing...", username, "Not using cached data, fresh processing...")
        output = gpt_utils.process_url(message, data_path, max_char_length=cfg["final_char_index"], model=cfg["MODEL"])
    if output['status'] == 'FAILED':
        server_utils.print_log("FAILED! RETURNING: " + str(output)[:150], username, "FAILED! RETURNING...")

        # since this failed, we allow the user to send another request, so we update their last_query_date.
        user.last_query_date = (datetime.datetime.now().astimezone() - datetime.timedelta(seconds=(cfg["TIME_DIFF_USER_REQ_SEC"]+1))).strftime(server_utils.date_time_format)
        db.session.commit()

        return {'output': output['output'], 'error': 'True'}

    output["date"] = message["date"]
    query_id = str(uuid.uuid4())

    db.session.add(
        UserQuery(
            id=query_id, 
            url=message["URL"], 
            good_bad_flag=0,
            date=output["date"],
            model_output=output["model_output"],
            model_output_parsed=output["output"],
            original_web=output["original_web"],
            cleaned_text=output["cleaned_text"],
            title=output["title"],
            is_private=False if message["web_html"] == "" else True,
            from_cached_query=output['from_cached_query'] if 'from_cached_query' in output else '',
            marked_text='',
            user_id=user_id,
            style_name=message["style"],
            )
    )
    user = User.query.filter_by(id=user_id).first()
    user.remaining_queries = user.remaining_queries - output['gpt_credits']
    user.last_query_date = output["date"]

    db.session.commit()

    user_output = {
        'query_id': query_id,
        'url': message["URL"],
        'title': output["title"],
        'output': output["output"],
        'error': 'False'}

    server_utils.print_log('PROCESS RETURNING TO USER: ' + str(user_output)[:150], username, 'PROCESS RETURNING TO USER')

    return user_output
    
@app.route('/processmarked', methods=['POST'])
@jwt_required()
def processmarked():
    '''
        This is similar to the process() method, but it takes a marked text as input, and processes it.
        Possible to merge the methods. Left for later.
    '''
    server_utils.print_log('PROCESS MARKED initiated! ' + str(datetime.datetime.now()))

    args = request.get_json()
    
    if not args or ("text" not in args) or args["text"] == "":
        return {"output": "No input detected. If you definitely selected some, try right clicking it and use Process marked text..."}

    server_utils.print_request_info(args)

    username = get_jwt_identity().lower()
    user = User.query.filter_by(name=username).first()
    if user is None:
        return {"output": "User not found."}
    user_id = user.id

    if not server_utils.user_has_credits(app, user, type='process'):
        return {"output": "Out of compute quota."}

    current_datetime = datetime.datetime.now().astimezone().strftime(server_utils.date_time_format)
    time_diff = (datetime.datetime.strptime(current_datetime, server_utils.date_time_format) - datetime.datetime.strptime(user.last_query_date, server_utils.date_time_format)).total_seconds()
    if time_diff < cfg["TIME_DIFF_USER_REQ_SEC"]:
        return {"output": "Please wait " + str(cfg["TIME_DIFF_USER_REQ_SEC"] - time_diff) + " seconds before sending another request."}
    user.last_query_date = current_datetime
    db.session.commit()

    message = {
        "URL": args["url"],
        "date": datetime.datetime.now().astimezone().strftime(server_utils.date_time_format), 
        "style": args["style"] if "style" in args else "",
        "sub_category": args["sub_category"] if "sub_category" in args else "",
        "req_id": args["req_id"] if "req_id" in args else '',
        "is_marked_text": True,
        "marked_text": args["text"]
    }

    should_use_cache, output = server_utils.should_use_cached_data(message, db, app, UserQuery, user_id)
    if should_use_cache:
        server_utils.print_log("Using cached data...", username, "Using cached data...")
    else:
        server_utils.print_log("Not using cached data, fresh processing...", username, "Not using cached data, fresh processing...")
        output = gpt_utils.process_url(message, data_path, max_char_length=cfg["final_char_index"], model=cfg["MODEL"])
    if output['status'] == 'FAILED':
        server_utils.print_log("FAILED! RETURNING: " + str(output)[:150], username, "FAILED! RETURNING...")
        return {'output': output['output']}

    output["date"] = message["date"]
    query_id = str(uuid.uuid4())

    db.session.add(
        UserQuery(
            id=query_id, 
            url=message["URL"], 
            good_bad_flag=0,
            date=output["date"],
            model_output=output["model_output"],
            model_output_parsed=output["output"],
            original_web=output["original_web"],
            cleaned_text=output["cleaned_text"],
            title=output["title"],
            is_private=True, # by default we mark it as private, as it can come from a private page
            from_cached_query=output['from_cached_query'] if 'from_cached_query' in output else '',
            marked_text=output['marked_text'],
            user_id=user_id,
            style_name=message["style"],
            )
    )
    user.remaining_queries = user.remaining_queries - output['gpt_credits']
    user.last_query_date = output["date"]

    db.session.commit()

    user_output = {
        'query_id': query_id,
        'url': message["URL"],
        'title': output["title"],
        'output': output["output"]}
    
    server_utils.print_log('PROCESSMARKED RETURNING TO USER: ' + str(user_output)[:150], username, 'PROCESSMARKED RETURNING TO USER')

    return user_output

@app.route('/reportquality', methods=['POST'])
@jwt_required()
def reportquality():
    server_utils.print_log('reportquality POST initiated')
    args = request.get_json()

    if "query_id" not in args or "flag" not in args:
        return {"Error": "Not enough parameters provided."}

    userquery = UserQuery.query.filter_by(id=args["query_id"]).first()
    if not userquery:
        return {"Error": "Query ID not found."}
    if args["flag"] == "good":
        userquery.good_bad_flag = 1
    elif args["flag"] == "bad":
        userquery.good_bad_flag = 2
    else:
        return {"Error": "Flag not recognized."}
    
    while userquery.from_cached_query != '':
        original_userquery = UserQuery.query.filter_by(id=userquery.from_cached_query).first()
        if args["flag"] == "good":
            original_userquery.good_bad_flag = 1
        elif args["flag"] == "bad":
            original_userquery.good_bad_flag = 2
        userquery = original_userquery

    db.session.commit()

    return {"Success": "Reported quality. Thanks!"}

@app.route('/savesession', methods=['POST'])
@jwt_required()
def savesession():
    server_utils.print_log('savesession POST initiated')

    args = request.get_json()

    if not server_utils.enough_input_params(args, ["data", "divider"]):
        return {"Error": "Not enough parameters provided."}

    username = get_jwt_identity().lower()
    return server_utils.save_session(args["data"], args["divider"], username, app, db, User)

@app.route('/deletesession', methods=['POST'])
@jwt_required()
def deletesession():
    print('deletequery POST initiated')

    args = request.get_json()
    username = get_jwt_identity().lower()

    if not server_utils.enough_input_params(args, ["subject", "session_id"]):
        return {"Error": "Not enough parameters provided."}

    return server_utils.delete_session(args["subject"], args["session_id"], username, app, db, User)

@app.route('/movequery', methods=['POST'])
@jwt_required()
def movequery():
    print('movequery POST initiated')

    args = request.get_json()
    
    if not server_utils.enough_input_params(args, ["saved_query_id", "original_divider_name", "new_divider_name", "original_divider_index", "new_divider_index"]):
        return {"Error": "Not enough parameters provided."}

    return 

@app.route('/adddivider', methods=['POST'])
@jwt_required()
def adddivider():
    print('adddivider POST initiated')

    args = request.get_json()
    server_utils.print_request_info(args)

    if not server_utils.enough_input_params(args, ["new_divider_name"]):
        return {"Error": "Not enough parameters provided."}

    username = get_jwt_identity().lower()

    return server_utils.add_divider(args["new_divider_name"], username, app, db, User)

@app.route('/deletedivider', methods=['POST'])
@jwt_required()
def deletedivider():
    args = request.get_json()

    if not server_utils.enough_input_params(args, ["divider_name"]):
        return {"Error": "Not enough parameters provided."}

    user_id = get_jwt_identity().lower()

    return server_utils.delete_divider(args["divider_name"], user_id, app, db, User)

@app.route('/signup', methods=['POST'])
def signup():
    args = request.get_json()
    for param in ["username", "password"]:
        if param not in args:
            return {"Error": "Not enough parameters provided."}
    server_utils.print_log('SIGNUP REQUEST: ' + str(args["username"]))

    signup_response = server_utils.signup_user(
        args["username"], 
        args["password"], 
        app,
        db,
        User)

    if signup_response["success"] == False:
        server_utils.print_log('SIGNUP FAILED: ' + signup_response["message"])
        return {"Error": signup_response["message"]}
    else:
        server_utils.print_log('SIGNUP SUCCESS: ' + signup_response["message"])
        return {"Success": signup_response["message"]}

@app.route('/login', methods=['POST'])
def login():
    args = request.get_json()
    if not server_utils.enough_input_params(args, ["username", "password"]):
        return {"Error": "Not enough parameters provided."}
    
    login_response = server_utils.login_user(
        args["username"],
        args["password"],
        app,
        db,
        User)

    if login_response["success"] == False:
        return {"Error": login_response["message"], "logged_in": False}

    access_token = create_access_token(identity=args["username"].lower())

    remaining_queries_questions = server_utils.get_remaining_queries_and_questions(args["username"], app, db, User)

    return {
        "Success": login_response["message"], 
        "logged_in": True, 
        "jwt_token": access_token,
        "remaining_queries": remaining_queries_questions["remaining_queries"],
        "remaining_questions": remaining_queries_questions["remaining_questions"]}

@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    args = request.get_json()
    
    username = get_jwt_identity().lower()
    
    jti = get_jwt()["jti"]
    jwt_cache_blocklist.set(jti, "")

    return {"Success": "True"}

@app.route('/loginjwt', methods=['POST'])
@jwt_required()
def loginjwt():
    server_utils.print_log('loginjwt POST initiated')

    verify_jwt_in_request()
    current_user = get_jwt_identity().lower()
    
    server_utils.print_log('CURRENT USER: ' + str(current_user))

    remaining_queries_questions = server_utils.get_remaining_queries_and_questions(current_user, app, db, User)
    return {
        "output": "Success logging-in: " + str(current_user), 
        "logged_in": True,
        "username": current_user,
        "remaining_queries": remaining_queries_questions["remaining_queries"],
        "remaining_questions": remaining_queries_questions["remaining_questions"]}

@app.route('/getsavedqueries', methods=['POST'])
@jwt_required()
def getsavedqueries():
    server_utils.print_log('getsavedqueries POST initiated')

    args = request.get_json()
    
    current_user = get_jwt_identity().lower()

    if not server_utils.enough_input_params(args, []):
        return {"Error": "Not enough parameters provided."}

    saved_dividers = server_utils.get_saved_data(current_user, app, db, User)
    return saved_dividers # return [{'key': 1, 'subject': 'sub', 'content': [{'id': 1, 'title': 'test1', 'url': 'http://example.com', 'short_summary': 'short summary', 'long_summary': {'activity': 'to test'}}]}]

@app.route('/feedback', methods=['POST'])
def feedback():
    server_utils.print_log('feedback POST initiated')

    args = request.get_json()
    print(args)
    for param in ['contactInfo', 'feedback']:
        if param not in args:
            return {"Error": "Not enough parameters provided."}

    server_utils.save_feedback(args['contactInfo'], args['feedback'])

    return {'Success': 'Feedback saved. Thanks.'}

@app.route('/getstyles', methods=['POST'])
@jwt_required()
def getstyles():
    server_utils.print_log('getstyles POST initiated')

    args = request.get_json()
    
    if not server_utils.enough_input_params(args, []):
        return {"Error": "Not enough parameters provided."}

    styles = server_utils.get_styles(app, db, Style)

    return {'styles': styles}

@app.route('/question', methods=['POST'])
@jwt_required()
def question():
    server_utils.print_log('question POST initiated')
    
    args = request.get_json()
    
    server_utils.print_request_info(args)

    if not server_utils.enough_input_params(args, ["question", "url"]):    
        return {"Error": "Not enough parameters provided."}
    marked_text = args["marked_text"] if ("marked_text" in args) else None
    qa_list = args["qa_list"] if ("qa_list" in args) else None
    chat_mode = (args["chat_mode"] if ("chat_mode" in args) else False) or args["question"].startswith('/chat')
    web_html = server_utils.handle_web_html(args)
 
    username = get_jwt_identity().lower()
    user_id = User.query.filter_by(name=username).first().id
    user = User.query.filter_by(id=user_id).first()

    if not server_utils.user_has_credits(app, user, type='question'):
        return {"output": "Out of compute quota.", "answer": "Out of compute quota.", "supporting_quote": ""}

    current_datetime = datetime.datetime.now().astimezone().strftime(server_utils.date_time_format)
    time_diff = (datetime.datetime.strptime(current_datetime, server_utils.date_time_format) - datetime.datetime.strptime(user.last_query_date, server_utils.date_time_format)).total_seconds()
    if time_diff < cfg["TIME_DIFF_USER_REQ_SEC"]:
        return {"answer": "Please wait " + str(cfg["TIME_DIFF_USER_REQ_SEC"] - time_diff) + " seconds before sending another request.", "supporting_quote": ''}
    user.last_query_date = current_datetime
    db.session.commit()

    if not chat_mode:
        print('QUESTION about PAGE')
        answer, backend_answer, supporting_quote = server_utils.get_answer_on_url(args["question"], args["url"], marked_text, web_html, qa_list, data_path, username)
        if backend_answer == {}:
            print('BACKEND ANSWER EMPTY')
            user.last_query_date = (datetime.datetime.now().astimezone() - datetime.timedelta(seconds=(cfg["TIME_DIFF_USER_REQ_SEC"]+1))).strftime(server_utils.date_time_format)
            db.session.commit()
            return {"answer": answer, "supporting_quote": '', 'error': True}
        
        db.session.add(UserQuestion(
            id=str(uuid.uuid4()),
            url=args["url"],
            question=args["question"],
            model_prompt=backend_answer["model_prompt"],
            answer=answer,
            date=current_datetime,
            is_private=True if ((marked_text and len(marked_text) > 0) or len(web_html) > 0) else False,
            from_cached_query=False,
            good_bad_flag=0,
            marked_text=backend_answer["marked_text"],
            original_web=backend_answer["original_web"],
            cleaned_text=backend_answer["cleaned_web"],
            user_id=user_id,
        ))
    else:
        print('QUESTION for CHAT')
        answer, backend_answer = server_utils.get_answer_on_chat(args["question"], qa_list, data_path, username)
        if backend_answer == {}:
            user.last_query_date = (datetime.datetime.now().astimezone() - datetime.timedelta(seconds=(cfg["TIME_DIFF_USER_REQ_SEC"]+1))).strftime(server_utils.date_time_format)
            db.session.commit()
            return {"answer": answer, "supporting_quote": '', 'error': True}
        
        supporting_quote = ''


    user.remaining_questions = user.remaining_questions - 1

    db.session.commit()

    print('RETURNED ANSWER ON QUESTION')
    if user.user_type == 'admin':
        print('ANSWER: ' + answer)

    return {"answer": answer, "supporting_quote": supporting_quote, 'error': False}

@app.route('/exportsession', methods=['POST'])
@jwt_required()
def exportsession():
    server_utils.print_log('exportsession POST initiated')

    args = request.get_json()
    server_utils.print_request_info(args)
    if not server_utils.enough_input_params(args, ["url", "title", "output", "qa_list"]):    
        return {"Error": "Not enough parameters provided."}

    csv_id = server_utils.get_csv_of_session(args["url"], args["title"], args["output"], args["qa_list"], data_path)
    if csv_id is None:
        return {"Error": "Session not found. This might happen if you tried to export sample results."}

    with open(os.path.join(data_path, 'export_csvs/' + csv_id + '.csv'), 'r') as f:
        csv = f.read()

    response = make_response(csv)
    response.headers["Content-Disposition"] = "attachment; filename=data.csv"
    response.headers["Content-type"] = "text/csv"

    return response

@app.route('/exporttonotion', methods=['POST'])
@jwt_required()
def exporttonotion():
    server_utils.print_log('exporttonotion POST initiated')

    args = request.get_json()
    server_utils.print_request_info(args)
    if not server_utils.enough_input_params(args, ["session", "database_id"]):    
        return {"Error": "Not enough parameters provided."}

    username = get_jwt_identity().lower()

    response = server_utils.export_to_notion(args["session"], args["database_id"], username, User, NotionRequest, app)

    return response

@app.route('/exportdivider', methods=['POST'])
@jwt_required()
def exportdivider():
    server_utils.print_log('exportdivider POST initiated')

    args = request.get_json()
    server_utils.print_request_info(args)

    if not server_utils.enough_input_params(args, ["divider_subject"]):    
        return {"Error": "Not enough parameters provided."}

    user = get_jwt_identity().lower()
    csv_id = server_utils.get_csv_of_divider(user, args["divider_subject"], app, db, User, data_path)
    if csv_id is None:
        return {"Error": "Divider not found. This might happen if you tried to export sample results."}

    with open(os.path.join(data_path, 'export_csvs/' + csv_id + '.csv'), 'r') as f:
        csv = f.read()
    
    response = make_response(csv)
    response.headers["Content-Disposition"] = "attachment; filename=data.csv"
    response.headers["Content-type"] = "text/csv"

    return response

@app.route('/getautotitle', methods=['POST'])
@jwt_required()
def getautotitle():
    server_utils.print_log('getautotitle POST initiated ' + str(datetime.datetime.now()))

    args = request.get_json()

    if not server_utils.enough_input_params(args, ["titles"]):    
        return {"Error": "Not enough parameters provided."}
    
    title = server_utils.get_auto_title(args["titles"])
    if title is None:
        return {"Error": "Cannot generate title.", "title": ""}
    else:
        return {"title": title}

@app.route('/requestaccess', methods=['POST'])
def requestaccess():
    '''
        This method registers the input e-mail to a datapool.
        Currently not used.
    '''
    args = request.get_json()
    print(args)
    if not server_utils.enough_input_params(args, ["email", "list_name"]):
        return cfg["ERROR_NOT_ENOUGH_PARAMS"]
    
    server_utils.save_email_to_waiting_list(data_path, args["list_name"], args["email"])

    return {"output": "The address " + args["email"] + " has been registered. We will get back to you soon."}

@app.route('/forgotpassword', methods=['POST'])
def forgotpassword():
    '''
        This method sends a password reset link to the input e-mail.
    '''
    server_utils.print_log('forgotpassword POST initiated')
    args = request.get_json()

    if not server_utils.enough_input_params(args, ["username"]):
        return cfg["ERROR_NOT_ENOUGH_PARAMS"]
    
    server_utils.send_password_reset_link(args["username"], app, db, User)

    return {"output": "returned."}

@app.route('/setnewpassword', methods=['POST'])
def setnewpassword():
    '''
        This method resets the password of the input user.
    '''
    server_utils.print_log('setnewpassword POST initiated')

    args = request.get_json()
    if not server_utils.enough_input_params(args, ["username", "password", "token"]):
        return cfg["ERROR_NOT_ENOUGH_PARAMS"]
    
    server_utils.set_new_password(args["username"], args["token"], args["password"], app, db, User)

    return {"output": "Successfully changed password."}

@app.route('/updatequota', methods=['POST'])
def updatequota():
    '''
        This method updates the quota of the input user.
    '''
    server_utils.print_log('updatequota POST initiated')

    args = request.get_json()
    if (not server_utils.enough_input_params(args, ["username", "new_queries", "new_questions", "code"])) and (not server_utils.enough_input_params(args, ["allowed_number_of_users", "code"])):
        return cfg["ERROR_NOT_ENOUGH_PARAMS"]
    
    output1 = {}
    if server_utils.enough_input_params(args, ["username", "new_queries", "new_questions", "code"]):
        output1 = server_utils.update_user_quota(args["username"], args["new_queries"], args["new_questions"], args["code"], app, db, User)

    output2 = {}
    if server_utils.enough_input_params(args, ["allowed_number_of_users"]):
        output2 = server_utils.update_allowed_number_of_users(args["allowed_number_of_users"], app, db, User, DBVariable)
    
    server_utils.init_server_utils(data_path, DBVariable, app, db)

    output = {**output1, **output2}

    return output

@app.route('/generatenotiontoken', methods=['POST'])
@jwt_required()
def generatenotiontoken():
    '''
        This method returns the notion token of the input user.
    '''
    server_utils.print_log('GENERATE-NOTION-TOKEN POST initiated' )

    username = get_jwt_identity().lower()

    notion_id = server_utils.generate_notion_token_id(username, app, db, User, NotionRequest)

    return {"success": True, "notion_id": notion_id}

'''
    MAIN METHOD
    This is only executed in debugging. In production, the server is launched from the gunicorn command.
    As it initializes some of the database, we run this once in debugging to initialize the database. (then, replace confirmation "n" with "y")
'''
if __name__ == '__main__':
    print('Launching server...')

    # code for resetting database. Uncomment to allow resetting.
    # confirmation = input("Are you sure you want to reset the database? (y/n): ")
    confirmation = "n"
    if confirmation == "y":
        with app.app_context():
            # reset db
            db.drop_all()
            db.create_all()

            # add several db rows
            db.session.add(Style(id=1, code_name="generic", front_name="Generic"))
            db.session.add(Style(id=2, code_name="travel", front_name="Travel"))
            db.session.add(Style(id=3, code_name="bizanalytics", front_name="Biz. Analytics"))
            db.session.add(Style(id=4, code_name="spaper", front_name="Scientific Paper"))
            db.session.add(Style(id=5, code_name="legal", front_name="Legal"))
            db.session.add(Style(id=6, code_name="news", front_name="News"))
            db.session.add(Style(id=7, code_name="bulletsgeneric", front_name="Generic Bullets"))

            db.session.commit()

    if debug_flag:
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    else:
        app.run(ssl_context=('/data/fullchain.pem', '/data/privkey.pem'), host='0.0.0.0', port=443, debug=False)
