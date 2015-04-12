# -*- coding: utf-8 -*-

import os
import urllib.parse
import flask
import logging
from rauth import OAuth1Service

from . import model

app = flask.Flask(__name__)

app_debug_flag = os.environ["DEBUG_SERVER"] == "TRUE"

app.config.update(
    SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
    DEBUG = app_debug_flag
)
app.logger.setLevel(logging.DEBUG if app_debug_flag else logging.WARNING)

# twitter経由のログイン
twitter = OAuth1Service(
    consumer_key=os.environ["TWITTER_CONSUMER_KEY"],
    consumer_secret=os.environ["TWITTER_CONSUMER_SECRET"],
    name='twitter',
    request_token_url='https://api.twitter.com/oauth/request_token',
    access_token_url='https://api.twitter.com/oauth/access_token',
    authorize_url='https://api.twitter.com/oauth/authenticate',
    base_url='https://api.twitter.com/1.1/'
)

# データベースの起動
model.model_init()

class UserInfo:
    @staticmethod
    def is_login():
        return "login" in flask.session

    @staticmethod
    def login(user_id, login_type, display_name):
        flask.session["login"] = {"user_id" : user_id,
                                  "type" : login_type,
                                  "display_name" : display_name}
    @staticmethod
    def logout():
        flask.session.pop('login', None)

    @staticmethod
    def get_login_type():
        return flask.session["login"]["type"]

    @staticmethod
    def get_user_display_name():
        return flask.session["login"]["display_name"]

    @staticmethod
    def get_user_id():
        return flask.session["login"]["user_id"]



# ルーティング
@app.before_request
def before_request():
    pass


@app.route("/")
def index():
    """ トップページ　ログイン状態か否かで表示を変える """
    loginout = '''
        <a href="./login/twitter">
        <img src="./static/img/sign-in-with-twitter-gray.png" alt="sign in with twitter"/>
        </a>'''
    if UserInfo.is_login():
        if UserInfo.get_login_type() == model.LOGIN_TYPE_TWITTER:
            loginout = '{0} <a href="./logout">ログアウト</a>'.format(
                UserInfo.get_user_display_name())

    return flask.render_template("index.html", loginout=loginout)


@app.route("/login/twitter")
def login_with_twitter():
    """ TwitterのOauth認証 """
    oauth_callback = flask.url_for('login_with_twitter_callback', _external=True)
    params = {'oauth_callback': oauth_callback}
    try:
        request_token, request_token_secret = twitter.get_request_token()
        flask.session["twitter_oauth"] = (request_token, request_token_secret)
    except:
        return "", 500

    return flask.redirect(twitter.get_authorize_url(request_token, **params))


@app.route("/login/twitter/callback")
def login_with_twitter_callback():
    """ TwitterのOauth認証の結果 """
    try:
        app.logger.info("#### login_with_twitter_callback ####")
        request_token, request_token_secret = flask.session["twitter_oauth"]

        creds = {'request_token': request_token,
                'request_token_secret': request_token_secret}
        params = {'oauth_verifier': flask.request.args['oauth_verifier']}
        sess = twitter.get_auth_session(params=params, **creds)
        verify = sess.get("account/verify_credentials.json").json()
        app.logger.info("twitter login success({0},{1})".format(verify["screen_name"], verify["id"]))
        new_user = model.User(name = str(verify["id"]), login_type = model.LOGIN_TYPE_TWITTER)
        user_id = model.add_user(new_user)
        # ログイン状態をセッションに保存
        UserInfo.login(user_id, new_user.login_type, verify["screen_name"])
    except:
        app.logger.info("twitter login fail")

    return flask.redirect("/")


@app.route('/logout')
def logout():
    UserInfo.logout() # ログイン状態を解除
    app.logger.info('You were signed out')
    return flask.redirect(flask.request.referrer or flask.url_for('index'))


@app.route("/api/add_new_drink", methods=["POST"])
def api_add_new_drink():
    """ 管理する飲み物を追加する"""
    if UserInfo.is_login():
        if "drink_name" not in flask.request.form:
            return "invalid data", 400
        drink_name = urllib.parse.unquote(flask.request.form['drink_name'])
        data_dict = model.append_drink_list(UserInfo.get_user_id(), drink_name)
        data_dict["name"] = drink_name
        return flask.jsonify(data_dict), 200
    else:
        return "not login", 403


@app.route("/api/drink/<drink_id>", methods=["PUT"])
def put_drink(drink_id):
    """ 飲んだカウンターの上げ下げ """
    print("put_drink")
    count = int(flask.request.form['update_count'])

    if UserInfo.is_login():
        print(UserInfo.get_user_id(), drink_id, count)
        if model.add_drink_history(UserInfo.get_user_id(), drink_id, count):
            return "OK", 200
        else:
            app.logger.error("DB error")
            return "db error", 400
    else:
        return "not login", 400


@app.route("/api/<drink_id>/stat", methods=["GET"])
def get_drink_stat(drink_id):
    """飲んだ履歴の取得"""
    if UserInfo.is_login():
        data = model.get_drink_history_stat(UserInfo.get_user_id(), drink_id)
        return data, 200
    else:
        return "not login", 400
    return "[]", 200


@app.route("/api/all_drink_list", methods=["GET"])
def get_all_drink_list():
    """飲み物一覧を取得 json format"""
    if UserInfo.is_login():
        all_drink = model.get_drink_list_by_json(UserInfo.get_user_id())
        return all_drink, 200
    else:
        return "[]", 200
