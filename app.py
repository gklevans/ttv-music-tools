from flask import Flask, request, url_for, redirect, render_template
import requests
import pandas as pd
from bs4 import BeautifulSoup

app = Flask(__name__)

@app.route('/', methods=['GET','POST'])
def home():
    if request.method == 'POST':
        streamer_name = request.form.get('streamer_name')
        requester_name = request.form.get('requester_name')
        musescore = request.form.get('musescore')
        return redirect(url_for('generate_history', 
                                strmr=streamer_name, 
                                rqstr=requester_name,
                                msscr=musescore))
    
    return render_template('home.html')

@app.route('/settings/', methods=['GET','POST'])
def settings():
    if request.method == "POST":
        streamer_name = request.form.get('streamer_name')
        return redirect(url_for('streamer', streamer_name=streamer_name))

    return redirect(url_for('home'))

@app.route("/settings/<streamer_name>")
def streamer(streamer_name):
    if(streamer_name == None):
        return redirect(url_for('home'))
    streamer = streamer_name.lower()
    streamer_url = 'https://api.streamersonglist.com/v1/streamers/' + streamer
    streamer_data = requests.get(streamer_url)
    if streamer_data.status_code == 400:
        return str(streamer_name) + ' was not found in StreamerSonglist.'
    streamer_data = streamer_data.json()
    
    #get standard request requirements
    canAnonymousRequest = streamer_data['canAnonymousRequest']
    canUserRequest = streamer_data['canUserRequest']
    canFollowerRequest = streamer_data['canFollowerRequest']
    canSubscriberRequest = streamer_data['canSubscriberRequest']
    canSubscriberT2Request = streamer_data['canSubscriberT2Request']
    canSubscriberT3Request = streamer_data['canSubscriberT3Request']
    
    user = canUserRequest
    follower = user or canFollowerRequest
    t1 = follower or canSubscriberRequest
    t2 = t1 or canSubscriberT2Request
    t3 = t2 or canSubscriberT3Request
        
    #get attributes
    attributes = streamer_data['attributes']
    attributes = [a for a in attributes]
                  #if a['showSelector'] == True or a['show'] == True]
    attributes = pd.json_normalize(attributes)
    
    #determine request requirement for a song with a given attribute
    def requestLevel(a):
        if not a['active']:
            return 6 - (user + follower + t1 + t2 + t3)
            #determined by general request requirements
        elif a['minAmount'] != None and a['minAmount'] > 0:
            return 7
        elif user and not (a['followerOnly'] or a['subscriberOnly']):
            return 1 #requestable by a logged-in user not following/subscribed
        elif follower and not a['subscriberOnly']:
            return 2 #requestable by a non-subscribed follower
            #need to follow
        elif t1 and (not a['subscriberOnly'] or (
                a['subTier'] == None or int(a['subTier']) < 2)):
            return 3 #requestable by a follower subscribed at Tier 1
            #need a Tier 1 sub
        elif t2 and (not a['subscriberOnly'] or (
               a['subTier'] == None or int(a['subTier']) < 3)):
            return 4 #requestable by a follower subscribed at Tier 2
            #need a Tier 2 sub
        elif t3:
            return 5 #requestable by a follower subscribed at Tier 3
            #need a Tier 3 sub
        else:
            return 6 #other
        
    if(len(attributes) > 0):
        attribute_reqs = attributes[['id','followerOnly','subscriberOnly',
                                     'subTier','active','minAmount']]
        attribute_reqs['reqLevel'] = attribute_reqs.apply(lambda a: 
                                                          requestLevel(a), 
                                                          axis=1)
        attribute_reqs = dict(attribute_reqs[['id','reqLevel']].values)
        
    #get songs
    streamer_id = str(streamer_data['id'])
    url = 'https://api.streamersonglist.com/v1/streamers/'
    songlist_url = url + streamer_id
    
    def songs_page(page):
        songs_url = songlist_url + '/songs?size=100&current=' + str(page)
        return requests.get(songs_url).json()
    
    songs_data = songs_page(0)
    sl_len = songs_data['total']
    songs = songs_data['items']
    
    if sl_len > 100:
        for page in range(1, 1 + sl_len // 100):
            songs += songs_page(page)['items']
    
    songs = pd.json_normalize(songs)[['id','title','artist','attributeIds']]
    
    #get request requirement for each song based on its attributes
    def maxReqLevel(atts):
        if atts == []:
            maxReqLevel = 6 - (user + follower + t1 + t2 + t3)
            return maxReqLevel
        else:
            maxReqLevel = max([attribute_reqs[atts[a]] 
                               for a in range(len(atts))])
            return maxReqLevel
        
    songs['reqLevel'] = songs.apply(lambda s: 
                                    maxReqLevel(s['attributeIds']), axis=1)
    
    reqLevelDict = {1 : 'any logged-in user.<br>',
                    2 : 'any follower.<br>',
                    3 : 'any Tier 1 subscriber.<br>',
                    4 : 'any Tier 2 subscriber.<br>',
                    5 : 'any Tier 3 subscriber.<br>',
                    6 : 'nobody through StreamerSonglist.<br>',
                    7 : 'donation.<br>'}
    
    other = ''; howMany = '<p>'; minFound = False; minReq = 0
    msg = '<p>Out of ' + str(sl_len) + ' active songs in the songlist:<br>'
    if sl_len == 1:
        msg = msg.replace('songs', 'song')
    for i in range(1,8):
        q = len(songs[songs['reqLevel']==i])
        if q > 0:
            if not minFound:
                minFound = True
                minReq = i
            howMany = str(q)
            if q == sl_len:
                howMany = 'All'
            if q == 1: 
                msg += howMany + other + ' song is' 
            else:
                msg += howMany + other + ' songs are'
            msg += ' requestable by ' + reqLevelDict[i]
            other = ' other'
    msg = msg[:-4] + '</p>'
        
    limitAnonymousRequests = streamer_data['limitAnonymousRequests']
    limitUserRequests = streamer_data['limitUserRequests']
    limitFollowerRequests = streamer_data['limitFollowerRequests']
    limitSubscriberRequests = streamer_data['limitSubscriberRequests']
    limitSubscriberT2Requests = streamer_data['limitSubscriberT2Requests']
    limitSubscriberT3Requests = streamer_data['limitSubscriberT3Requests']
    
    requestsPerAnon= streamer_data['requestsPerAnonymous']
    requestsPerUser = streamer_data['requestsPerUser']
    requestsPerFollower = streamer_data['requestsPerFollower']
    requestsPerSub = streamer_data['requestsPerSub']
    requestsPerSubTier2 = streamer_data['requestsPerSubTier2']
    requestsPerSubTier3 = streamer_data['requestsPerSubTier3']
    
    conRequestsPerAnon= streamer_data['concurrentRequestsPerAnonymous']
    conRequestsPerUser = streamer_data['concurrentRequestsPerUser']
    conRequestsPerFollower = streamer_data['concurrentRequestsPerFollower']
    conRequestsPerSub = streamer_data['concurrentRequestsPerSub']
    conRequestsPerSubTier2 = streamer_data['concurrentRequestsPerSubTier2']
    conRequestsPerSubTier3 = streamer_data['concurrentRequestsPerSubTier3']
    
    requestsActive = streamer_data['requestsActive']
    
    info = '<h3>Here are the queue settings for '+str(streamer_name)+'.</h3>'
    
    limits = ''
    #end_of_line = ' request(s) per stream'
    def lim_sentence(req, conreq):
        sentence = str(req)
        if req == 1:
            sentence += ' request per stream and '
        else:
            sentence += ' requests per stream and '
        if conreq == 1:
            sentence += str(conreq) + ' concurrent request.'
        else:
            sentence += str(conreq) + ' concurrent requests.'
        return sentence
    
    reqsLimited = True
    reqLimits = 0
    conReqLimits = 0
    
    if(canAnonymousRequest and minReq == 1):
        limits += '<br>Anonymous users are allowed ' 
        reqsLimited = reqsLimited and limitAnonymousRequests
        if(reqsLimited):
            reqLimits = max(reqLimits, requestsPerAnon)
            conReqLimits = max(conReqLimits, conRequestsPerAnon)
            limits += lim_sentence(reqLimits, conReqLimits)
        else:
            limits += 'unlimited requests per stream.'
    if(canUserRequest and minReq == 1):
        limits += '<br>Logged-in users are allowed ' 
        reqsLimited = reqsLimited and limitUserRequests
        if(reqsLimited):
            reqLimits = max(reqLimits, requestsPerUser)
            conReqLimits = max(conReqLimits, conRequestsPerUser)
            limits += lim_sentence(reqLimits, conReqLimits)
        else:
            limits += 'unlimited requests per stream.'
    if(canFollowerRequest and minReq < 3):
        limits += '<br>Followers are allowed '
        reqsLimited = reqsLimited and limitFollowerRequests
        if(reqsLimited):
            reqLimits = max(reqLimits, requestsPerFollower)
            conReqLimits = max(conReqLimits, conRequestsPerFollower)
            limits += lim_sentence(reqLimits, conReqLimits)
        else:
            limits += 'unlimited requests per stream.'
    if(canSubscriberRequest and minReq < 4):
        limits += '<br>Tier 1 subs are allowed '
        reqsLimited = reqsLimited and limitSubscriberRequests
        if(reqsLimited):
            reqLimits = max(reqLimits, requestsPerSub)
            conReqLimits = max(conReqLimits, conRequestsPerSub)
            limits += lim_sentence(reqLimits, conReqLimits)
        else:
            limits += 'unlimited requests per stream.'
    if(canSubscriberT2Request and minReq < 5):
        limits +='<br>Tier 2 subs are allowed '
        reqsLimited = reqsLimited and limitSubscriberT2Requests
        if(reqsLimited):
            reqLimits = max(reqLimits, requestsPerSubTier2)
            conReqLimits = max(conReqLimits, conRequestsPerSubTier2)
            limits += lim_sentence(reqLimits, conReqLimits)
        else:
            limits += 'unlimited requests per stream.'
    if(canSubscriberT3Request and minReq < 6):
        limits = limits + '<br>Tier 3 subs are allowed ' 
        reqsLimited = reqsLimited and limitSubscriberT3Requests
        if(reqsLimited):
            reqLimits = max(reqLimits, requestsPerSubTier3)
            conReqLimits = max(conReqLimits, conRequestsPerSubTier3)
            limits += lim_sentence(reqLimits, conReqLimits)
        else:
            limits += 'unlimited requests per stream.'
    limits = limits[4:]
    
    if(requestsActive):
        info += '<p> The queue is currently open.</p>'
    else:
        info += '<p> The queue is currently closed.</p>'
            
    info += """<p><i> Below are the settings when the queue is open.
                    </i></p>"""
    info += msg + limits
    
    # allowLiveLearns = streamer_data['allowLiveLearns']
    # minLiveLearnAmount = streamer_data['minLiveLearnAmount']
    # if allowLiveLearns:
    #     info += '<p>Live-learns are enabled'
    #     if minLiveLearnAmount > 0:
    #         info += ' for a minimum of $' + str(minLiveLearnAmount)
    # else:
    #     info += '<p>Live-learns are disabled'
    # info += '.</p>'
    
    minutesBetweenRequests = streamer_data['minutesBetweenRequests']
    def timeBetweenRequests(minutes):
        hours = minutes // 60; days = hours // 24; weeks = days // 7
        minutes %= 60; hours %= 24; days %= 7; time = ''
        units = {'week': weeks, 'day': days, 'hour': hours, 'minute': minutes}
        for unit in units:
            value = units[unit]
            if value > 0:
                time += str(value) + ' ' + unit + ', '
            if value > 1:
                time = time[:-2] + 's, ' 
        time = time[:-2] + '.'
        return time
    if minutesBetweenRequests > 0:
        info += """<p>The cooldown period after which a song may be requested
                again is """ + timeBetweenRequests(minutesBetweenRequests)
    
    html = """
    <!DOCTYPE html>
    <html lang="en">
    
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Songlist Settings</title>
        <style>
        body {background-color: lightgray;}
        </style>
    </head>""" + info + """<p></p>
    <form action="/" method="GET">
        <button type="submit">Return Home</button>
    </form>
    </body>
    
    </html>
    """
    return html

@app.route("/history")
def generate_history():
    streamer_name = request.args.get('strmr')
    requester_name = request.args.get('rqstr')
    if(streamer_name == None or requester_name == None):
        return redirect(url_for('home'))
    streamer_url = 'https://api.streamersonglist.com/v1/streamers/'
    streamer_url = streamer_url + str(streamer_name).lower()
    streamer_data = requests.get(streamer_url)
    if streamer_data.status_code == 400:
        return str(streamer_name) + ' was not found in StreamerSonglist.'
    streamer_data = streamer_data.json()

    #get streamer id
    streamer_id = str(streamer_data['id'])
    
    #get streamersonglist url
    songlist_url = 'https://api.streamersonglist.com/v1/streamers/'
    songlist_url = songlist_url + streamer_id
    
    #get request history
    history_url = songlist_url + '/playHistory?size=100000'  
    history_data = requests.get(history_url).json()
    history = history_data['items']
    if len(history) == 0:
        return str(streamer_name) + ' has no history of requests.'
    history = pd.json_normalize(history)
    
    #clean up columns
    def requester(i):
        try: return history['requests'][i][0]['name']
        except: pass
    names = [requester(i) for i in range(len(history))]
    dates = [history['playedAt'][i][0:10] for i in range(len(history))]
    history['requester'] = names
    history['Date'] = dates
    history.drop(['createdAt','donationAmount','requests','note'], 
                 axis=1, inplace=True)
    
    history_filtered = history[
        history['requester'].str.lower()==str(requester_name).lower()]
    if len(history_filtered) == 0:
        return f"""{requester_name} has no history of requests in 
                {streamer_name}'s channel."""
    history_filtered.reset_index(inplace=True)
    history_filtered = history_filtered[[
        'Date','song.title','song.artist','nonlistSong']]
    
    #get titles from musescore links
    def ms_title(ll):
        if isinstance(ll, str):
            ms = next(filter(lambda w: 
                             'musescore.com/' in w, ll.split()), None)
            if (ms == None):
                return None
            try:
                webpage = requests.get(ms).text
                soup = BeautifulSoup(webpage, "html.parser")
                title = soup.find('meta', property='og:title')['content']
                return title
            except:
                return 'Could not find title'
            
    musescore = request.args.get('msscr')
    if musescore == 'on':
         ms_titles = [ms_title(history_filtered['nonlistSong'][i]) 
                      for i in range(len(history_filtered))]
         history_filtered['Musescore Title'] = ms_titles
    history_filtered.fillna("", inplace=True)
    history_filtered.rename({"nonlistSong" : "Non-Songlist Requests",
                             "song.title" : "Title",
                             "song.artist" : "Artist"
                             }, axis=1, inplace=True)

    table_html = history_filtered.to_html(table_id="table", index=False)
    
    html =  f"""
    <html>
    <head>
    <link 
    href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.min.css" 
    rel="stylesheet">
    <title>Songlist History</title>
    </head>
    <p style="background-color: silver;">
    <b>Here is {requester_name}'s history of requests in 
    {streamer_name}'s channel.</b></p>
    {table_html}
    <script src="https://code.jquery.com/jquery-3.6.0.slim.min.js" 
    integrity="sha256-u7e5khyithlIdTpu22PHhENmPcRdFiHRjhAuHcs05RI=" 
    crossorigin="anonymous"></script>
    <script type="text/javascript" 
    src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js">
    </script>
    <script>
    $(document).ready( function () {{
        $('body').css("background-color","silver");
        $('#table').DataTable({{
            order: [[0, 'desc']],
            }});
        }});
    </script>
    <p></p>
    <form action="/" method="GET">
    <button type="submit">Return Home</button>
    </form>
    </body>
    </html>
    """
    return html