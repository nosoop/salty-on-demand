# -*- coding: utf-8 -*-

# https://github.com/Damiya/saltspy

from socketIO_client import SocketIO
import requests
import subprocess, os, signal, re, time, random
import websocket

import _thread as thread

def safe_print(*objects, errors = 'ignore', **kwargs):
    '''
    I really don't want to have to bother with fixing up all my texts when printing, so here's
    an ascii-only print function
    '''
    print( *(t.encode('ascii', errors = errors).decode('ascii') for t in objects), **kwargs )

current_state = None
stream_dump_pid = None
filename = None

def on_sb_event(*args):
    global current_state
    global stream_dump_pid
    global filename
    
    if len(args):
        match_request = requests.get('http://saltybet.com/state.json')
        match = match_request.json()
        
        # debounce to avoid checking the same result
        if match['status'] == current_state:
            return
        
        current_state = match['status']
        
        # this is almost the same way the site does tournament detection, don't blame me
        is_tournament_final = 'FINAL ROUND' in match['remaining']
        is_tournament_round = is_tournament_final or 'bracket' in match['remaining']
        
        is_matchmaking = 'until the next tournament' in match['remaining']
        
        if match['status'] == 'open':
            print('betting open for {p1name} vs. {p2name}'.format(**match))
            
            p1 = re.sub('\s+', '_', match['p1name'].upper())
            p2 = re.sub('\s+', '_', match['p2name'].upper())
            
            filename = '{time}_{p1}_vs_{p2}'.format(p1 = p1, p2 = p2, time = int(time.time()))
            
            # if is_tournament_round or not is_matchmaking:
            if is_tournament_round or is_matchmaking:
                # TODO stop recording of previous match if mismatched
                stream_dump_pid = subprocess.Popen([ 'youtube-dl', '--restrict-filenames',
                        '-f', '480p', '--quiet', '-o', filename + '.mp4',
                        'http://twitch.tv/saltybet' ]).pid
                print('salty on demand: recording match')
        elif match['status'] == 'locked':
            print('betting closed for {p1name} vs. {p2name}'.format(**match))
        else:
            if match['status'] == '1':
                print('{p1name} won, paid out to RED'.format(**match))
            elif match['status'] == '2':
                print('{p1name} won, paid out to BLUE'.format(**match))
            else:
                print('unknown state {status}'.format(**match))
            
            if (any(status == match['status'] for status in [ '1', '2'])
                    and stream_dump_pid is not None):
                # youtube-dl passes SIGINT to the ffmpeg instance and closes the video properly
                os.kill(stream_dump_pid, signal.SIGINT)
                stream_dump_pid = None

def chat_thread():
    global stream_dump_pid
    
    def on_chat_opened(ws):
        # https://discuss.dev.twitch.tv/t/twitch-tv-web-browser-chat/6186/2
        ws.send('CCAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership')
        ws.send('NICK justinfan' + str(random.randint(1, 131072)))
        ws.send('JOIN #saltybet')
    
    def on_chat_message(ws, message):
        global stream_dump_pid
        if message.startswith('PING'):
            # PING :tmi.twitch.tv
            action, reply = message.split(maxsplit = 1)
            
            ws.send('PONG ' + reply[1:].rstrip())
            
            return
        
        # print(message.encode('ascii', errors = 'backslashreplace').decode('utf8'))
        userinfo, action, *action_opt = message.split(maxsplit = 2)
        action_info, *_ = action_opt or [ None ]
        
        user, *_ = userinfo[1:].split('!')
        
        # channel message
        if action == 'PRIVMSG':
            channel, *text_content = action_info.split()
            text = ' '.join(text_content).rstrip()[1:]
            safe_print(user + ':', text, errors = 'backslashreplace')
            
            # TODO stop recording if is_tournament and saltybet says
            # 'Exhibitions will start shortly. Thanks for watching! wtfSALTY'
            # or 'Tournament will start shortly.'
            # saltybet doesn't send a payout event until after advertisements
            if user == 'saltybet' and 'Exhibitions will start shortly' in text:
                if stream_dump_pid is not None:
                    os.kill(stream_dump_pid, signal.SIGINT)
                    stream_dump_pid = None
    
    ws = websocket.WebSocketApp('wss://irc-ws.chat.twitch.tv/', on_message = on_chat_message)
    ws.on_open = on_chat_opened
    ws.run_forever()

thread.start_new_thread(chat_thread, ())

socketIO = SocketIO('http://www-cdn-twitch.saltybet.com', 1337)
socketIO.on('message', on_sb_event)
socketIO.wait()
ws.run_forever()

