#This file is responsible for all the functionality
from config import *
import mysql.connector
from colorama import init, Fore
import redis
import bcrypt
import datetime
import requests
from discord_webhook import DiscordWebhook, DiscordEmbed
import time

init() #initialises colourama for colours

print(f"""{Fore.BLUE}  _____            _ _     _   _ _    _____                 _ _ 
 |  __ \          | (_)   | | (_) |  |  __ \               | | |
 | |__) |___  __ _| |_ ___| |_ _| | _| |__) |_ _ _ __   ___| | |
 |  _  // _ \/ _` | | / __| __| | |/ /  ___/ _` | '_ \ / _ \ | |
 | | \ \  __/ (_| | | \__ \ |_| |   <| |  | (_| | | | |  __/ |_|
 |_|  \_\___|\__,_|_|_|___/\__|_|_|\_\_|   \__,_|_| |_|\___|_(_)
 ---------------------------------------------------------------
{Fore.RESET}""")

Allowed = [3145727, 918015, 1048575] #Ill replace this later when i understand the privilege system

try:
    mydb = mysql.connector.connect(
        host=UserConfig["SQLHost"],
        user=UserConfig["SQLUser"],
        passwd=UserConfig["SQLPassword"]
    ) #connects to database
    print(f"{Fore.GREEN} Successfully connected to MySQL!")
except Exception as e:
    print(f"{Fore.RED} Failed connecting to MySQL! Abandoning!\n Error: {e}{Fore.RESET}")
    exit()

try:
    r = redis.Redis(host=UserConfig["RedisHost"], port=UserConfig["RedisPort"], db=UserConfig["RedisDb"]) #establishes redis connection
    print(f"{Fore.GREEN} Successfully connected to Redis!")
except Exception as e:
    print(f"{Fore.RED} Failed connecting to Redis! Abandoning!\n Error: {e}{Fore.RESET}")
    exit()

mycursor = mydb.cursor() #creates a thing to allow us to run mysql commands
mycursor.execute(f"USE {UserConfig['SQLDatabase']}") #Sets the db to ripple

def DashData():
    #note to self: add data caching so data isnt grabbed every time the dash is accessed
    """Grabs all the values for the dashboard"""
    mycursor.execute("SELECT * FROM system_settings")
    Alert = mycursor.fetchall()[2][3] #Not the best way but it's fast!!
    if Alert == "": #checks if no aler
        Alert = False
    response = {
        "RegisteredUsers" : r.get("ripple:registered_users").decode("utf-8") ,
        "OnlineUsers" : r.get("ripple:online_users").decode("utf-8") ,
        "Alert" : Alert
    }
    return response

def LoginHandler(username, password):
    """Checks the passwords and handles the sessions"""
    mycursor.execute(f"SELECT username, password_md5, ban_datetime, privileges, id FROM users WHERE username_safe = '{username.lower()}'")
    User = mycursor.fetchall()
    if len(User) == 0:
        #when user not found
        return [False, "User not found. Maybe a typo?"]
    else:
        User = User[0]
        #Stores grabbed data in variables for easier access
        Username = User[0]
        PassHash = User[1]
        IsBanned = User[2]
        Privilege = User[3]
        id = User = User[4]
        
        #Converts IsBanned to bool
        if IsBanned == "0":
            IsBanned = False
        else:
            IsBanned = True

        #shouldve been done during conversion but eh
        if IsBanned:
            return [False, "You are banned... Awkward..."]
        else:
            if Privilege in Allowed: #password checking doesnt work yet. sad.
                #and bcrypt.checkpw(str(password).encode('utf-8'), str(PassHash).encode('utf-8'))
                return [True, "You have been logged in!", { #creating session
                    "LoggedIn" : True,
                    "AccountId" : id,
                    "AccountName" : Username,
                    "Privilege" : Privilege
                }]
            else:
                return [False, "Missing privileges!"]

def TimestampConverter(timestamp):
    """Converts timestamps into readable time"""
    date = datetime.datetime.fromtimestamp(int(timestamp)) #converting into datetime object
    #so we avoid things like 21:6
    hour = str(date.hour)
    minute = str(date.minute)
    #if len(hour) == 1:
        #hour = "0" + hour
    if len(minute) == 1:
        minute = "0" + minute
    return f"{hour}:{minute}"

def RecentPlays():
    """Returns recent plays"""
    #this is probably really bad
    mycursor.execute("SELECT scores.beatmap_md5, users.username, scores.userid, scores.time, scores.score, scores.pp, scores.play_mode, scores.mods FROM scores LEFT JOIN users ON users.id = scores.userid WHERE users.privileges & 1 ORDER BY scores.id DESC LIMIT 10")
    plays = mycursor.fetchall()
    if UserConfig["HasRelax"]:
        #adding relax plays
        mycursor.execute("SELECT scores_relax.beatmap_md5, users.username, scores_relax.userid, scores_relax.time, scores_relax.score, scores_relax.pp, scores_relax.play_mode, scores_relax.mods FROM scores_relax LEFT JOIN users ON users.id = scores_relax.userid WHERE users.privileges & 1 ORDER BY scores_relax.id DESC LIMIT 10")
        playx_rx = mycursor.fetchall()
        for plays_rx in playx_rx:
            #addint them to the list
            plays_rx = list(plays_rx)
            plays_rx.append("RX")
            plays.append(plays_rx)
    PlaysArray = []
    #converting into lists as theyre cooler (and easier to work with)
    for x in plays:
        PlaysArray.append(list(x))

    #converting the data into something readable
    ReadableArray = []
    for x in PlaysArray:
        #yes im doing this
        #lets get the song name
        BeatmapMD5 = x[0]
        mycursor.execute(f"SELECT song_name FROM beatmaps WHERE beatmap_md5 = '{BeatmapMD5}'")
        SongFetch = mycursor.fetchall()
        if len(SongFetch) == 0:
            #checking if none found
            SongName = "Invalid..."
        else:
            SongName = list(SongFetch[0])[0]
        #make and populate a readable dict
        Dicti = {}
        Dicti["Player"] = x[1]
        Dicti["PlayerId"] = x[2]
        #if rx
        if x[-1] == "RX":
            Dicti["SongName"] = SongName + " +Relax"
        else:
            Dicti["SongName"] = SongName
        Dicti["Score"] = f'{x[4]:,}'
        Dicti["pp"] = round(x[5])
        Dicti["Time"] = TimestampConverter(x[3])
        ReadableArray.append(Dicti)
    
    ReadableArray = sorted(ReadableArray, key=lambda k: k["Time"]) #sorting by time
    ReadableArray.reverse()
    return ReadableArray

def FetchBSData():
    mycursor.execute("SELECT name, value_string, value_int FROM bancho_settings WHERE name = 'bancho_maintenance' OR name = 'menu_icon' OR name = 'login_notification'")
    Query = list(mycursor.fetchall())
    #bancho maintenence
    if Query[0][2] == 0:
        BanchoMan = False
    else:
        BanchoMan = True
    return {
        "BanchoMan" : BanchoMan,
        "MenuIcon" : Query[1][1],
        "LoginNotif" : Query[2][1]
    }

def BSPostHandler(post, session):
    BanchoMan = post[0]
    MenuIcon = post[1]
    LoginNotif = post[2]

    #setting blanks to bools
    if BanchoMan == "On":
        BanchoMan = True
    else:
        BanchoMan = False
    if MenuIcon == "":
        MenuIcon = False
    if LoginNotif == "":
        LoginNotif = False

    #SQL Queries
    if MenuIcon != False: #this might be doable with just if not BanchoMan
        mycursor.execute(f"UPDATE bancho_settings SET value_string = '{MenuIcon}', value_int = 1 WHERE name = 'menu_icon'")
    else:
        mycursor.execute("UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'menu_icon'")

    if LoginNotif != False:
        mycursor.execute(f"UPDATE bancho_settings SET value_string = '{LoginNotif}', value_int = 1 WHERE name = 'login_notification'")
    else:
        mycursor.execute("UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'login_notification'")

    if BanchoMan:
        mycursor.execute("UPDATE bancho_settings SET value_int = 1 WHERE name = 'bancho_maintenance'")
    else:
        mycursor.execute("UPDATE bancho_settings SET value_int = 0 WHERE name = 'bancho_maintenance'")
    
    mydb.commit()
    RAPLog(session["AccountId"], "modified the bancho settings")

def GetBmapInfo(id):
    """Gets beatmap info"""
    mycursor.execute(f"SELECT beatmapset_id FROM beatmaps WHERE beatmap_id = '{id}'")
    Data = mycursor.fetchall()
    if len(Data) == 0:
        #it might be a beatmap set then
        mycursor.execute(f"SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked FROM beatmaps WHERE beatmapset_id = '{id}'")
        BMS_Data = mycursor.fetchall()
        if len(BMS_Data) == 0: #if still havent found anything

            return [{
                "SongName" : "Not Found",
                "Ar" : "0",
                "Difficulty" : "0",
                "BeatmapsetId" : "",
                "BeatmapId" : 0,
                "Cover" : "https://a.ussr.pl/" #why this? idk
            }]
    else:
        BMSID = Data[0][0]
        mycursor.execute(f"SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked FROM beatmaps WHERE beatmapset_id = '{BMSID}'")
        BMS_Data = mycursor.fetchall()
    BeatmapList = []
    for beatmap in BMS_Data:
        thing = { 
            "SongName" : beatmap[0],
            "Ar" : str(beatmap[1]),
            "Difficulty" : str(round(beatmap[2], 2)),
            "BeatmapsetId" : str(beatmap[3]),
            "BeatmapId" : str(beatmap[4]),
            "Ranked" : beatmap[5],
            "Cover" : f"https://assets.ppy.sh/beatmaps/{beatmap[3]}/covers/cover.jpg"
        }
        BeatmapList.append(thing)
    BeatmapList =  sorted(BeatmapList, key = lambda i: i["Difficulty"])
    #assigning each bmap a number to be later used
    BMapNumber = 0
    for beatmap in BeatmapList:
        BMapNumber = BMapNumber + 1
        beatmap["BmapNumber"] = BMapNumber
    return BeatmapList

def HasPrivilege(session):
    """Check if the person trying to access the page has perms to do it."""
    if session["LoggedIn"] and session["Privilege"] in Allowed:
        return True
    else:
        return False

def RankBeatmap(BeatmapNumber, BeatmapId, ActionName, session):
    """Ranks a beatmap"""
    #converts actions to numbers
    if ActionName == "Loved":
        ActionName = 5
    elif ActionName == "Ranked":
        ActionName = 2
    elif ActionName == "Unranked":
        ActionName = 0
    else:
        print(" Received alien input from rank. what?")
        return
    try:
        mycursor.execute(f"UPDATE beatmaps SET ranked = {ActionName}, ranked_status_freezed = 1 WHERE beatmap_id = {BeatmapId} LIMIT 1")
        mycursor.execute(f"UPDATE scores s JOIN (SELECT userid, MAX(score) maxscore FROM scores JOIN beatmaps ON scores.beatmap_md5 = beatmaps.beatmap_md5 WHERE beatmaps.beatmap_md5 = (SELECT beatmap_md5 FROM beatmaps WHERE beatmap_id = {BeatmapId} LIMIT 1) GROUP BY userid) s2 ON s.score = s2.maxscore AND s.userid = s2.userid SET completed = 3")
        mydb.commit()
        Webhook(BeatmapId, ActionName, session)
        return True
    except Exception as e:
        print(" An error occured while ranking!\n " + str(e))
        return False

def Webhook(BeatmapId, ActionName, session):
    """Beatmap rank webhook"""
    URL = UserConfig["Webhook"]
    if URL == "":
        #if no webhook is set, dont do anything
        return
    headers = {'Content-Type': 'application/json'}
    mycursor.execute(f"SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmap_id = {BeatmapId}")
    mapa = mycursor.fetchall()
    mapa = mapa[0]
    if ActionName == 0:
        TitleText = "unranked :("
    if ActionName == 2:
        TitleText = "ranked!"
    if ActionName == 5:
        TitleText = "loved!"
    webhook = DiscordWebhook(url=URL) #creates webhook
    # me trying to learn the webhook
    #EmbedJson = { #json to be sent to webhook
    #    "image" : f"https://assets.ppy.sh/beatmaps/{mapa[1]}/covers/cover.jpg",
    #    "author" : {
    #        "icon_url" : f"https://a.ussr.pl/{session['AccountId']}",
    #        "url" : f"https://ussr.pl/b/{BeatmapId}",
    #        "name" : f"{mapa[0]} was just {TitleText}"
    #    },
    #    "description" : f"Ranked by {session['AccountName']}",
    #    "footer" : {
    #        "text" : "via RealistikPanel!"
    #    }
    #}
    #requests.post(URL, data=EmbedJson, headers=headers) #sends the webhook data
    embed = DiscordEmbed(description=f"Ranked by {session['AccountName']}", color=242424) #this is giving me discord.py vibes
    embed.set_author(name=f"{mapa[0]} was just {TitleText}", url=f"https://ussr.pl/b/{BeatmapId}", icon_url=f"https://a.ussr.pl/{session['AccountId']}")
    embed.set_footer(text="via RealistikPanel!")
    embed.set_image(url=f"https://assets.ppy.sh/beatmaps/{mapa[1]}/covers/cover.jpg")
    webhook.add_embed(embed)
    print(" * Posting webhook!")
    webhook.execute()
    RAPLog(session["AccountId"], f"ranked/unranked the beatmap {mapa[0]} ({BeatmapId})")

def RAPLog(UserID=999, Text="forgot to assign a text value :/"):
    """Logs to the RAP log"""
    Timestamp = round(time.time())
    #now we putting that in oh yea
    mycursor.execute(f"INSERT INTO rap_logs (userid, text, datetime, through) VALUES ({UserID}, '{Text}', {Timestamp}, 'RealistikPanel!')")
    mydb.commit()