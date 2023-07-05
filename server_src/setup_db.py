'''
We design the database schema in this file.
Currently, the app has several functionalities:
1) it allows a user to submit a query to the backend, possibly with a "style"/"category"
2) it allows a user to save a query to their "bookmarks"
3) it allows a user to rank a query result as "good" or "bad"

'''
'''
Creating the database according to digitalocean tutorial: (https://www.digitalocean.com/community/tutorials/how-to-use-flask-sqlalchemy-to-interact-with-databases-in-a-flask-application)

export FLASK_APP=app
flask shell
'''

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id                  = db.Column(db.String(80), primary_key=True)               # unique id for each user, probably based on uuid4
    name                = db.Column(db.String(80), unique=False, nullable=False)   # user name is not unique
    email               = db.Column(db.String(80), unique=True, nullable=False)    # user email is unique
    password            = db.Column(db.String(80), unique=False, nullable=False)   # user password is stored in plaintext. This is not a good practice, but it's ok for now
    api_key             = db.Column(db.Text, unique=False, nullable=False)         # the api key for the user, if we choose user to be in charge of that
    last_query_date     = db.Column(db.String(40), unique=False, nullable=False)   # date-time of last query, based on date_time_format from server.py
    signup_date         = db.Column(db.String(40), unique=False, default='2023-03-01 00:00:01')   # date-time of signup, based on date_time_format from server_utils.py
    saved_dividers      = db.Column(db.Text, nullable=False, default='[]')         # kind of a mini-DB by itself. Each key is a divider name, and each value is a list of queries
    last_saved_query    = db.Column(db.JSON, nullable=False, default={})           # the last query saved by the user, intended to be shown when the user reopens the app
    
    forgot_pw_token     = db.Column(db.String(80), unique=False, default=None)     # whether the user forgot their password
    
    user_type           = db.Column(db.String(20), unique=False, nullable=False)   # whether the user is a "normal" user or an "admin" user
    remaining_queries   = db.Column(db.Integer, unique=False, default=0)           # how many queries the user has left for the current time-cycle
    remaining_questions = db.Column(db.Integer, unique=False, default=0)           # how many questions the user has left for the current time-cycle
    char_limit          = db.Column(db.Integer, unique=False, nullable=False)      # allowing the user a maximum characters per time-cycle. May likely change in future

    notion_access_token = db.Column(db.String(80), default='')        # the access token for the user's notion account
    
    def __repr__(self):
        return '<User %r>' % self.name

class Style(db.Model):
    __tablename__ = 'styles'
    code_name    = db.Column(db.String(60), primary_key=True, nullable=False)   # code name of the style, used in the backend; we find no good reason for an id right now
    front_name   = db.Column(db.String(60), nullable=False)                     # front name of the style, used in the frontend
    id           = db.Column(db.Integer)                                        # id of the style, currently not used
    
    def __repr__(self):
        return '<Style %r>' % self.code_name

class UserQuery(db.Model):
    __tablename__ = 'user_queries'
    id                  = db.Column(db.String(80), primary_key=True)                            # unique id for each query, probably based on uuid4
    url                 = db.Column(db.String(1024), unique=False, nullable=False)              # url of the query
    good_bad_flag       = db.Column(db.Integer, unique=False, nullable=False, default=0)        # whether the user thinks the query result is good or bad. 0 - undetermined. 1 - good. 2 - bad
    date                = db.Column(db.String(40), unique=False, nullable=False)                # date-time of query, based on date_time_format from server.py
    model_output        = db.Column(db.Text, unique=False, nullable=False)                      # raw output from the model
    model_output_parsed = db.Column(db.JSON, unique=False, nullable=False)                      # parsed model output - a dictionary
    original_web        = db.Column(db.Text, unique=False, nullable=False)                      # original web text, probably HTML
    cleaned_text        = db.Column(db.Text, unique=False, nullable=False)                      # cleaned text from the web page, after jusText or another text cleaner
    is_private          = db.Column(db.Boolean, unique=False, nullable=False, default=True)     # whether the query is based on private data
    from_cached_query   = db.Column(db.String(80), unique=False, nullable=False, default='')    # whether the query is based on a cached query. If no - '', if yes, id.
    marked_text         = db.Column(db.Text, unique=False, nullable=False, default='')          # marked text from the user. If none, ''.
    user_id             = db.Column(db.String(80), db.ForeignKey('users.id'))                   # user who made the request
    style_name          = db.Column(db.String(60), db.ForeignKey('styles.code_name'))           # style of the query
    title               = db.Column(db.String(256), unique=False, nullable=True)                # model-generated title of the query
    user = db.relationship('User', foreign_keys=[user_id], lazy=True)
    style = db.relationship('Style', foreign_keys=[style_name], lazy=True)

    def __repr__(self):
        return f'<URL %r>' % self.url

class UserQuestion(db.Model):
    __tablename__ = 'user_questions'
    id                  = db.Column(db.String(80), primary_key=True)                            # unique id for each question, probably based on uuid4
    url                 = db.Column(db.String(1024), unique=False, nullable=False)              # url of the query
    question            = db.Column(db.Text, unique=False, nullable=False)                      # the question itself
    model_prompt        = db.Column(db.Text, unique=False, nullable=False)                      # the prompt for the model
    answer              = db.Column(db.Text, unique=False, nullable=False)                      # the answer to the question
    date                = db.Column(db.String(40), unique=False, nullable=False)                # date-time of question, based on date_time_format from server.py
    is_private          = db.Column(db.Boolean, unique=False, nullable=False, default=True)     # whether the query is based on private data
    from_cached_query   = db.Column(db.String(80), unique=False, nullable=False, default='')    # whether the query is based on a cached query. If no - '', if yes, id.
    good_bad_flag       = db.Column(db.Integer, unique=False, nullable=False, default=0)        # whether the user thinks the query result is good or bad. 0 - undetermined. 1 - good. 2 - bad. We will determine the functionality of setting this flag later. One possibility - if the user deletes the question, we assume it's bad
    marked_text         = db.Column(db.Text, unique=False, nullable=False, default='')          # marked text from the user. If none, ''.
    original_web        = db.Column(db.Text, unique=False, nullable=False)                      # original web text, probably HTML
    cleaned_text        = db.Column(db.Text, unique=False, nullable=False)                      # cleaned text from the web page, after jusText or another text cleaner

    user_id             = db.Column(db.String(80), db.ForeignKey('users.id'))                   # user who made the request

    user = db.relationship('User', foreign_keys=[user_id], lazy=True)
    
    def __repr__(self):
        return f'<QA %r>' % self.question

class NotionRequest(db.Model):
    __tablename__ = 'notion_request'
    id                  = db.Column(db.String(50), primary_key=True)                            # unique id for each notion request, based on uuid4
    status              = db.Column(db.String(20), unique=False, nullable=False)                # status of the request. Can be 'pending', 'success', 'error'
    date                = db.Column(db.String(40), unique=False, nullable=False)                # date-time of notion request, based on date_time_format from server_utils.py
    user_id             = db.Column(db.String(80), db.ForeignKey('users.id'))                   # user who made the request
    response_details    = db.Column(db.Text, unique=False, nullable=False, default='{}')        # response details from the notion API, including access_token, etc.
    
    user = db.relationship('User', foreign_keys=[user_id], lazy=True)
    
    def __repr__(self):
        return f'<NotionReq %r>' % self.id
    
class DBVariable(db.Model):
    __tablename__ = 'db_variable'
    name                  = db.Column(db.String(20), primary_key=True)                            # unique id for each notion request, based on uuid4
    value                 = db.Column(db.String(50), unique=False, nullable=False)                # status of the request. Can be 'pending', 'success', 'error'
    last_set_date         = db.Column(db.String(40), unique=False, nullable=False)                # date-time of notion request, based on date_time_format from server_utils.py
    
    def __repr__(self):
        return f'<DBVariable %r>' % self.name