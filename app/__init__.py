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
    init_list = ""

    if "login" in flask.session:
        if flask.session["login"]["type"] == model.LOGIN_TYPE_TWITTER:
            loginout = '{0} <a href="./logout">ログアウト</a>'.format(
                flask.session["login"]["display_name"])

        init_list = model.get_drink_list_by_html(flask.session["login"]["user_id"])

    return flask.render_template("index.html", loginout=loginout, initial_list=init_list)


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
        flask.session["login"] = {"user_id" : user_id,
                                  "type" : new_user.login_type,
                                  "display_name":verify["screen_name"]}
    except:
        app.logger.info("twitter login fail")

    return flask.redirect("/")


@app.route('/logout')
def logout():
    flask.session.pop('login', None) # ログイン状態を解除
    app.logger.info('You were signed out')
    return flask.redirect(flask.request.referrer or flask.url_for('index'))


@app.route("/api/add_drink", methods=["POST"])
def api_add_drink():
    """ 管理する飲み物を追加する"""
    if "login" in flask.session:
        if "drink_name" not in flask.request.form:
            return "invalid data", 400

        drink_name = urllib.parse.unquote(flask.request.form['drink_name'])
        data_dict = model.append_drink_list(flask.session["login"]["user_id"], drink_name)
        data_dict["name"] = drink_name
        return flask.jsonify(data_dict), 200
    else:
        # 非ログイン状態
        return "not login", 403


@app.route("/api/drink/<drink_name>", methods=["PUT"])
def put_drink(drink_name):
    """ 飲んだカウンターの上げ下げ """
    print("put_drink")
    count = int(flask.request.form['update_count'])

    if "login" in flask.session:
        print(flask.session["login"]["user_id"], drink_name, count)

        if model.add_drink_history(flask.session["login"]["user_id"], drink_name, count):
            return "OK", 200
        else:
            app.logger.error("DB error")
            return "db error", 400
    else:
        # 非ログイン状態
        return "not login", 400


@app.route("/api/<drink_id>/stat", methods=["GET"])
def get_drink_stat(drink_id):
    """飲んだ履歴の取得"""

    if "login" in flask.session:
        data = model.get_drink_history_stat(flask.session["login"]["user_id"], drink_id)
        return data, 200
    else:
        return "not login", 400

    return "[]", 200
