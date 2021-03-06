# -*- coding: utf-8 -*-
import os
import datetime
import html
import json
import flask
import sqlalchemy as sql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm.session import sessionmaker

LOGIN_TYPE_SPECIAL = 0
LOGIN_TYPE_TWITTER = 1

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    user_id    = sql.Column(sql.Integer, primary_key=True)
    name       = sql.Column(sql.Text(256), nullable=False)
    login_type = sql.Column(sql.Integer, nullable=False)
    auth_key   = sql.Column(sql.Text(256))
    auth_pass  = sql.Column(sql.Text(256))

    def __repr__(self):
        return "<id={0} name={1}, login={2}, key={3}, pass={4}>".format(
            self.user_id, self.name, self.login_type, self.auth_key, self.auth_pass)

class Drink(Base):
    __tablename__ = "drinks"
    drink_id = sql.Column(sql.Integer, primary_key=True)
    name     = sql.Column(sql.Text(256), nullable=False)

    def __repr__(self):
        return "<drink_id={0} name={1}>".format(self.drink_id, self.name)

class DrinkList(Base):
    __tablename__ = "drink_list"
    list_id  = sql.Column(sql.Integer, primary_key=True)
    user_id  = sql.Column(sql.Integer,
                   sql.ForeignKey("users.user_id", onupdate="CASCADE", ondelete="CASCADE"),
                   nullable=False)
    drink_id = sql.Column(sql.Integer,
                   sql.ForeignKey("drinks.drink_id", onupdate="CASCADE", ondelete="CASCADE"),
                   nullable=False)
    index    = sql.Column(sql.Integer, nullable=False)

    def __repr__(self):
        return "<user_id={0} drink_id={1} index={2}>".format(
            self.user_id, self.drink_id, self.index)

class History(Base):
    __tablename__ = "history"
    history_id = sql.Column(sql.Integer, primary_key=True)
    user_id    = sql.Column(sql.Integer,
                     sql.ForeignKey("users.user_id", onupdate="CASCADE", ondelete="CASCADE"))
    drink_id   = sql.Column(sql.Integer,
                     sql.ForeignKey("drinks.drink_id", onupdate="CASCADE", ondelete="CASCADE"))
    count      = sql.Column(sql.Integer, nullable=False)
    datetime   = sql.Column(sql.DateTime, nullable=False)

    def __repr__(self):
        return "<history_id={0} user_id={1} drink_id={2} count={3} datetime={4}>".format(
            self.history_id, self.user_id, self.drink_id, self.coutn, self.datetime)


#データベースのアクセスを提供する関数
make_session = None

def model_init():
    SQLALCHEMY_DATABASE_URI = os.environ["SQLALCHEMY_DATABASE_URI"]
    engine = sql.create_engine(SQLALCHEMY_DATABASE_URI, encoding="utf-8")
    engine.echo = True if os.environ["DEBUG_SERVER"] == "TRUE" else False
    Base.metadata.create_all(engine)
    global make_session
    make_session = sessionmaker(bind=engine)



def _is_user_already_exists(name, login_type):
    """ ユーザーが登録済みか 登録済みなら user_id、されていなければ 0 を返す """
    db = None
    try:
        db = make_session()
        ret = (db.query(User).
               filter(User.name == name).
               filter(User.login_type == login_type)).first()
        if ret is None:
            return 0
        else:
            return ret.user_id
    finally:
        if db is not None:
            db.close()

def add_user(name, login_type):
    """  user_id を返す """
    user_id = _is_user_already_exists(name, login_type)
    if user_id == 0: # create new user
        db = None
        try:
            db = make_session()
            user = User(name=name, login_type=login_type)
            db.add(user)
            db.commit()
            db.refresh(user) # user_id を手に入れる (user_id は auto increament)
            user_id = user.user_id
        except:
            raise Exception;
        finally:
            if db is not None:
                db.close()

    return user_id

def _register_drink(name):
    """ drink(Drink), is_new(boolean) のタプルを返す """
    db = None
    try:
        db = make_session()
        ret = db.query(Drink).filter(Drink.name == name).first()
        is_new = ret is not None
        if not is_new:
            # 新しい飲み物の追加
            new_drink = Drink(name=name)
            db.add(new_drink)
            db.commit()
            db.refresh(new_drink)
            ret = new_drink
        return ret, is_new
    finally:
        if db is not None:
            db.close()

def add_new_drink(user_id, drink_name):
    """ 管理する飲み物を追加する
        戻り値: dict ["status"] <= "added" (今回追加した) or "already" (すでに存在する)
                dict ["index"] <= 表示順を示す整数(1以上)
    """
    drink, is_new = _register_drink(drink_name)
    db = None
    try:
        db = make_session()
        ret = (db.query(DrinkList).filter(DrinkList.user_id == user_id)
                                  .filter(DrinkList.drink_id == drink.drink_id)).first()
        if ret is not None:
            return {"status":"already"}
        # 新しく追加するものは最後尾に
        max_index = (db.query(sql.func.max(DrinkList.index).label("max_index")).
                     filter(DrinkList.user_id == user_id)).one()[0]
        if max_index is None:
            max_index = 0
        drink_list = DrinkList(user_id=user_id, drink_id=drink.drink_id, index=max_index+1)
        db.add(drink_list)
        db.commit()
        return {"status":"added", "drink_id": drink_list.drink_id, "index": drink_list.index}
    finally:
        if db is not None:
            db.close()

def get_drink_list_by_json(user_id):
    """ 現在の飲み物リストを生成する
        json文字列を返す
    """
    db = None
    try:
        db = make_session()
        ret = db.query(Drink.name,
                       sql.func.ifnull(sql.func.sum(History.count), 0),
                       DrinkList.index,
                       Drink.drink_id) \
                .select_from(DrinkList) \
                .join(Drink) \
                .outerjoin(History,
                      sql.and_(DrinkList.user_id == History.user_id,
                      DrinkList.drink_id == History.drink_id)) \
                .filter(DrinkList.user_id == user_id) \
                .group_by(Drink.drink_id).all()
        ret_obj = []
        for row in ret:
            ret_obj.append(
                {"name": str(row[0]),
                 "count":int(row[1]),
                 "index":int(row[2]),
                 "drink_id": int(row[3])})

        return json.dumps(ret_obj)
    finally:
        if db is not None:
            db.close()


def add_drink_history(user_id, drink_id, count):
    """ 飲んだ記録をつける 正常に処理できれば True を返す """
    db = None
    try:
        db = make_session()
        hist = History(
            user_id=user_id, drink_id=drink_id, count=count, datetime=datetime.datetime.now())
        db.add(hist)
        db.commit()
        return True
    except:
        return False
    finally:
        if db is not None:
            db.close()

def _generate_drink_history_stat_json(histories, range_type):
    """飲んだ履歴グラフ用のjsonを生成する"""
    if range_type == "30days":
        def convert_daystr(dt):
            return "{0:%Y-%m-%d}".format(dt)
        now = datetime.datetime.now()
        date_labels = [convert_daystr(now + datetime.timedelta(i)) for i in range(-29,1,1)]
        acc_counts = [0 for _ in range(30)] #その日までの累積値
        base_count = 0 # 30日前の時点の累積値

        for t in histories:
            try:
                idx = date_labels.index(convert_daystr(t.datetime))
                acc_counts[idx] += t.count
            except ValueError:
                base_count += t.count

        acc_counts[0] = acc_counts[0] + base_count
        for i in range(1, len(acc_counts)):
            acc_counts[i] = acc_counts[i] + acc_counts[i-1]

        output = [{"date":x[0], "count":x[1]} for x in zip(date_labels, acc_counts)]
        return json.dumps(output)
    else: # invalid range_type
        return "[]" # empty

def get_drink_history_stat(user_id, drink_id, range_type="30days"):
    """飲んだ履歴 json文字列を返す"""
    stat = []
    db = None
    try:
        db = make_session()
        stat = db.query(History) \
            .filter(History.user_id == user_id) \
            .filter(History.drink_id == drink_id) \
            .order_by(History.datetime).all()
    finally:
        if db is not None:
            db.close()

    return _generate_drink_history_stat_json(stat, range_type)
