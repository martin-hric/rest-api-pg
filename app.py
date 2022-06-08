# author: Martin Hric
# FIIT DBS 2022

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
import simplejson as json
import os
import psycopg2

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db_orm = SQLAlchemy(app)


def db_connect():
    dota2database = psycopg2.connect(
        database=os.environ.get('DB_NAME'),
        host=os.environ.get('DB_HOST'),
        port=os.environ.get('DB_PORT'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASS')
    )
    return dota2database
def db_close(db,cur):
    cur.close()
    db.close()

@app.route('/')
def base():
    return "<h1> homepage </h1>"

@app.route('/v1/health/')
def task1():
    dota2database = db_connect()
    cur = dota2database.cursor()
    cur.execute("SELECT VERSION();")
    version_tuple = cur.fetchone()
    cur.execute("SELECT pg_database_size('dota2')/1024/1024 as dota2_db_size;")
    size_tuple = cur.fetchone()
    db_close(dota2database,cur)

    value = dict()
    value['version'] = version_tuple[0]
    value['dota2_db_size'] = size_tuple[0]

    return jsonify(pgsql= value)

@app.route('/v2/patches/')
def task2_patches():
    dota2database = db_connect()
    cur = dota2database.cursor()
    v2_patches_query = """
    select
m.id,
cast(round(m.duration / 60.0,2) as numeric(36,2)),
subq.* from
(select p.name,
        cast(extract(epoch from p.release_date) as integer) as patch_start_date,
        lag(cast(extract(epoch from p.release_date) as integer), -1,  cast(extract(epoch from current_date) as integer)) over (order by p.id) as patch_end_date
        from patches as p

)as subq
left join matches as m on m.start_time between subq.patch_start_date and subq.patch_end_date
    """
    cur.execute(v2_patches_query)
    data = cur.fetchall()
    db_close(dota2database,cur)

    dict_matches = []
    dict_patches = []
    prev_ver = '6.70'
    prev_st = ''
    prev_end = ''

    for every_tuple in data:
        m_id, dur, ver, st, end = every_tuple

        if ver != prev_ver:
            dict_patches.append({"patch_version": prev_ver,
                                 "patch_start_date": prev_st,
                                 "patch_end_date": prev_end,
                                 "matches": dict_matches})
            dict_matches = []

        if m_id is not None:
            dict_matches.append({"match_id": m_id,
                                "duration": dur})
        else: dict_matches = []

        prev_ver = ver
        prev_st = st
        prev_end = end

    #posledny patch nie je v cykle, kedze vraciam end_date ako current_date v query ale v zadani sa vyzaduje null
    dict_patches.append({"patch_version": prev_ver,
                        "patch_start_date": prev_st,
                        "patch_end_date": None,
                        "matches": dict_matches})

    dict_v3 = {"patches": dict_patches}
    response = app.response_class(
        response=json.dumps(dict_v3),
        status=200,
        mimetype='application/json'
    )
    return response

@app.route('/v2/players/<player_id>/game_exp/')
def task2_game_exp(player_id):
    dota2database = db_connect()
    cur = dota2database.cursor()
    v2_exp_query = f"""
    select players.id,coalesce(players.nick,'unknown') , m.id,heroes.localized_name,cast(round(m.duration / 60.0,2) as numeric(36,2)),
coalesce(mpd.xp_hero,0) +coalesce(mpd.xp_creep,0) +coalesce(mpd.xp_other,0) +coalesce(mpd.xp_roshan,0),max(mpd.level) as xp,
bool((mpd.player_slot <= 4 and m.radiant_win is true) or (mpd.player_slot >4 and m.radiant_win is false))
from players inner join matches_players_details mpd on players.id = mpd.player_id
inner join heroes on mpd.hero_id = heroes.id
inner join matches m on mpd.match_id = m.id where players.id = {player_id}
group by m.id,players.nick,heroes.localized_name ,mpd.player_slot,mpd.xp_hero,mpd.xp_creep,mpd.xp_other , mpd.xp_roshan , players.id
    """
    cur.execute(v2_exp_query)
    data = cur.fetchall()
    db_close(dota2database,cur)

    dict_matches = []
    nick = ''
    p_id = ''
    for every_tuple in data:
        p_id,nick,m_id,hero_name,time,exp,level,win = every_tuple
        dict_matches.append({"match_id": m_id,
                             "hero_localized_name": hero_name,
                             "match_duration_minutes": time,
                             "experiences_gained": exp,
                             "level_gained": level,
                             "winner": win
                             })

    dict_final = {
        "id": p_id,
        "player_nick": nick,
        "matches": dict_matches
    }
    response = app.response_class(
        response=json.dumps(dict_final),
        status=200,
        mimetype='application/json'
    )
    return response

@app.route('/v2/players/<player_id>/game_objectives/')
def task2_objectives(player_id):
    dota2database = db_connect()
    cur = dota2database.cursor()
    v2_objectives_query = f"""
    select
players.id,
coalesce(players.nick,'unknown') ,h.localized_name,m.id,
coalesce(go.subtype,'NO_ACTION'),count(go.subtype)
from players left join matches_players_details mpd on players.id = mpd.player_id
left join matches m on mpd.match_id = m.id
left join heroes h on mpd.hero_id = h.id
left join game_objectives go on mpd.id = go.match_player_detail_id_1
where players.id = {player_id}
group by players.nick,h.localized_name, go.subtype, m.id, players.id
order by m.id
    """
    cur.execute(v2_objectives_query)
    data = cur.fetchall()

    db_close(dota2database,cur)
    dict_matches =[]
    dict_actions = []
    p_name= ''
    p_id = ''
    old_tuple = data[0]
    old_m_id = old_tuple[3]
    old_h_name = ''
    for every_tuple in data:
        p_id, p_name, h_name, m_id,action,count = every_tuple
        if count == 0: count= 1

        if m_id != old_m_id:
            dict_matches.append({"match_id": old_m_id,
                                 "hero_localized_name": old_h_name,
                                 "actions": dict_actions
                                 })
            dict_actions = []
        dict_actions.append({"hero_action": action,
                             "count": count
        })

        old_m_id = m_id
        old_h_name = h_name

    dict_matches.append({"match_id": old_m_id,
                         "hero_localized_name": old_h_name,
                         "actions": dict_actions
                         })
    dict_final = {
        "id": p_id,
        "player_nick": p_name,
        "matches": dict_matches
    }
    response = app.response_class(
        response=json.dumps(dict_final),
        status=200,
        mimetype='application/json'
    )
    return response

@app.route('/v2/players/<player_id>/abilities/')
def task2_abilities(player_id):
    dota2database = db_connect()
    cur = dota2database.cursor()
    v2_abilities_query = f"""
    select
players.id,coalesce(players.nick,'unknown'),h.localized_name, m.id , a.name , count(a.name), max(au.level) as level
from players left join matches_players_details mpd on players.id = mpd.player_id
left join matches m on mpd.match_id = m.id
left join ability_upgrades au on mpd.id = au.match_player_detail_id
left join abilities a on au.ability_id = a.id
left join heroes h on mpd.hero_id = h.id
where players.id = {player_id}
group by players.id, h.localized_name, m.id, a.name
order by m.id, h.localized_name
    """
    cur.execute(v2_abilities_query)
    data = cur.fetchall()
    db_close(dota2database,cur)

    dict_matches = []
    dict_abilities = []
    p_name = ''
    p_id = ''
    old_h_name = ''
    first_tuple = data[0]
    first_m_id = first_tuple[3]

    for every_tuple in data:
        p_id,p_name,h_name,m_id,h_ability,count,level = every_tuple

        if m_id != first_m_id:
            dict_matches.append({"match_id": first_m_id,
                                 "hero_localized_name": old_h_name,
                                 "abilities": dict_abilities})
            dict_abilities = []

        dict_abilities.append({"ability_name": h_ability,
                                "count": count,
                                "upgrade_level": level
                                })

        first_m_id = m_id
        old_h_name = h_name

    dict_matches.append({"match_id": first_m_id,
                         "hero_localized_name": old_h_name,
                         "abilities": dict_abilities})
    dict_final = {
        "id": p_id,
        "player_nick": p_name,
        "matches": dict_matches
    }
    response = app.response_class(
        response=json.dumps(dict_final),
        status=200,
        mimetype='application/json'
    )
    return response

@app.route('/v3/matches/<match_id>/top_purchases/')
def task3_purchases(match_id):
    dota2database = db_connect()
    cur = dota2database.cursor()
    v3_query_purchases = f"""
    with subq as(
select match_id as mid, hero_id as heroID, heroes.localized_name as heroNAME, items.id as itemID,items.name as itemNAME,count(items.id) as count,row_number() over(partition by hero_id order by hero_id, count(items.id) DESC, items.name) as rownumber
FROM players p
JOIN matches_players_details mpd on p.id = mpd.player_id
JOIN heroes on mpd.hero_id = heroes.id
JOIN matches on mpd.match_id = matches.id
JOIN purchase_logs on mpd.id = purchase_logs.match_player_detail_id
JOIN items on purchase_logs.item_id = items.id
WHERE match_id = {match_id} and bool((mpd.player_slot <= 4 and matches.radiant_win is true) or (mpd.player_slot >4 and matches.radiant_win is false))
group by hero_id, heroes.localized_name, items.id, items.name,mpd.match_id
order by hero_id, count DESC, items.name
)
select mid,heroID,heroNAME,itemID,itemNAME,count
from subq where rownumber <=5
    """
    cur.execute(v3_query_purchases)
    data = cur.fetchall()
    db_close(dota2database, cur)

    heroes = []
    top_purchases = []
    prev_heroID = data[0][1]
    prev_heroNAME = ''
    mid = ''

    for every_tuple in data:
        mid,heroID,heroNAME,itemID,itemNAME,count = every_tuple

        if heroID != prev_heroID:
            heroes.append({
                "id":prev_heroID,
                "name":prev_heroNAME,
                "top_purchases": top_purchases
            })
            top_purchases = []

        top_purchases.append({
            "id":itemID,
            "name":itemNAME,
            "count":count
        })

        prev_heroID = heroID
        prev_heroNAME = heroNAME

    heroes.append({
        "id": prev_heroID,
        "name": prev_heroNAME,
        "top_purchases": top_purchases
    })

    final_dict = {
        "id": mid,
        "heroes": heroes
    }
    response = app.response_class(
        response=json.dumps(final_dict),
        status=200,
        mimetype='application/json'
    )
    return response

@app.route('/v3/abilities/<ability_id>/usage/')
def task3_abilities(ability_id):
    dota2database = db_connect()
    cur = dota2database.cursor()
    v3_query_purchases = f"""
    select ability_id,ability_name,heroID,hero_name,winner,bucket,count(player_id) as count
from
    (select
        mpd.player_id, abilities.id as ability_id,abilities.name as ability_name,hero_id as heroID, h.localized_name as hero_name,
        bool((mpd.player_slot <= 4 and m.radiant_win is true) or (mpd.player_slot >4 and m.radiant_win is false)) as winner,
        case
            when (cast(au.time as float)/m.duration)*100.0 < 10 then '0-9'
            when (cast(au.time as float)/m.duration)*100.0 < 20 then '10-19'
            when (cast(au.time as float)/m.duration)*100.0 < 30 then '20-29'
            when (cast(au.time as float)/m.duration)*100.0 < 40 then '30-39'
            when (cast(au.time as float)/m.duration)*100.0 < 50 then '40-49'
            when (cast(au.time as float)/m.duration)*100.0 < 60 then '50-59'
            when (cast(au.time as float)/m.duration)*100.0 < 70 then '60-69'
            when (cast(au.time as float)/m.duration)*100.0 < 80 then '70-79'
            when (cast(au.time as float)/m.duration)*100.0 < 90 then '80-89'
            when (cast(au.time as float)/m.duration)*100.0 < 100 then '90-99'
            else '100-109'
        end as bucket
    from abilities
    join ability_upgrades au on abilities.id = au.ability_id
    join matches_players_details mpd on au.match_player_detail_id = mpd.id
    join heroes h on mpd.hero_id = h.id
    join matches m on mpd.match_id = m.id
    group by (abilities.id,abilities.name,hero_id,h.localized_name,mpd.player_slot,m.radiant_win,m.duration,au.time, mpd.player_id)
) as subq
where ability_id = {ability_id}
group by ability_id,ability_name,heroID,hero_name,winner,bucket
order by  subq.heroID,subq.winner ,count desc 
    """
    cur.execute(v3_query_purchases)
    data = cur.fetchall()
    db_close(dota2database, cur)

    heroes= []
    a_name = ''
    a_id = ''
    winners = {}
    losers = {}
    prev_hero_id = data[0][2]
    prev_h_name = ''
    win_count = 0
    lose_count = 0

    for every_tuple in data:
        a_id,a_name,h_id,h_name,win,bucket,count = every_tuple

        if h_id != prev_hero_id:
            heroes.append({
                "id": prev_hero_id,
                "name": prev_h_name,
                "usage_winners": winners,
                "usage_loosers": losers
            })
            winners = []
            losers = []
            win_count = 0
            lose_count = 0

        if win and win_count == 0:
            winners = {
                "bucket": bucket,
                "count": count
            }
            win_count += 1
        if not win and lose_count == 0:
            losers = {
                "bucket": bucket,
                "count": count + 1
            }
            lose_count += 1

        prev_hero_id = h_id
        prev_h_name = h_name

    heroes.append({
        "id": prev_hero_id,
        "name": prev_h_name,
        "usage_winners": winners
    })

    final_dict = {
        "id": a_id,
        "name": a_name,
        "heroes": heroes
    }
    response = app.response_class(
        response=json.dumps(final_dict),
        status=200,
        mimetype='application/json'
    )
    return response

if __name__ == '__main__':
    app.run()
