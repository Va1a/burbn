#This software has distribution limitations described in the LICENSE file
#BurbnBot IG API wrapper by github.com/Va1a

import requests
import json
import random
import hashlib
import hmac
import urllib
import uuid
import time
import cv2
import os

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class RateLimitError(Exception):
    pass

class InvalidDataError(Exception):
    pass

class BurbnBot:
    USER_AGENT = 'Instagram 137.0.0.17.122 Android (23/6.0; 480dpi; 1080x1920; unknown/Android; Android SDK built for x64; generic_x86; ranchu; en_US; 195415566)'
    API_BASE = 'https://i.instagram.com/api/v1'
    IG_SIG_KEY = '4f8732eb9ba7d1c8e8897a75d6474d4eb3f5279137431b2aafb71fafe2abe178'
    SIG_KEY_VERSION = '4'
    LOGFILE = None

    def __init__(self, username, password, useragent=None, logfile=None, verbose=False):
        if useragent is not None:
            self.USER_AGENT = useragent
        if logfile is not None:
            self.LOGFILE = logfile
        self.VERBOSE = verbose
        m = hashlib.md5()
        m.update(username.encode('utf-8') + password.encode('utf-8'))
        self.device_id = self.generateDeviceID(m.hexdigest())
        self._setUser(username, password)
        self.isLoggedIn = False
        self.LastResponse = None
        self.s = requests.Session()

    def _getCache(self):
        try:
            with open('.burbn_cache', 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            return self._writeCache({'ids': {'instagram': '25025320'}, 'cookies': {}})

    def _writeCache(self, data):
        with open('.burbn_cache', 'w+') as cache:
            json.dump(data, cache, indent=4)
        return

    def _setUser(self, username, password):
        self.username = username
        self.password = password
        self.uuid = self.generateUUID()

    # Stores cookies in the burbn cache.
    def saveCookies(self):
        cache = self._getCache()
        cache['cookies'] = requests.utils.dict_from_cookiejar(self.s.cookies)
        self._writeCache(cache)
        return True

    # Restores cookies stored in the burbn cache.
    def restoreCookies(self):
        cookies = self._getCache()['cookies']
        self.s.cookies.update(requests.utils.cookiejar_from_dict(cookies))
        self.csrf = cookies['csrftoken']
        self.username_id = cookies['ds_user_id']
        self.rank_token = f"{self.username_id}_{self.uuid}"
        self.login(fetch=False)
        return True

    # Logs in to the initialized account.
    def login(self, fetch=True):
        if fetch: self.send(f'/si/fetch_headers/?challenge_type=signup&guid={self.generateUUID(dashed=False)}')
        payload = {'phone_id': self.generateUUID(),
                '_csrftoken': (self.LastResponse.cookies['csrftoken'] if fetch else self.csrf),
                'username': self.username,
                'guid': self.uuid,
                'device_id': self.device_id,
                'password': self.password,
                'login_attempt_count': '0'}

        loginResp = self.send('/accounts/login/', data=self.sign(payload), login=True)
        self.isLoggedIn = True
        self.username_id = loginResp['logged_in_user']['pk']
        self.rank_token = f"{self.username_id}_{self.uuid}"
        self.csrf = self.LastResponse.cookies['csrftoken']
        return loginResp

    # Logs out the initialized account, if logged in.
    def logout(self):
        if not self.isLoggedIn:
            raise Exception('Logout called but no account logged in.')
        payload = {'phone_id': self.generateUUID(),
               '_csrftoken': self.csrf,
               'guid': self.uuid,
               'device_id': self.device_id,
               '_uuid': self.uuid
        }
        x = self.send('/accounts/logout/', self.sign(payload))
        self.isLoggedIn = False
        return x

    # Creates a new message thread with the provided username or user ID.
    def createMsgThread(self, text, username=None, userid=None):
        if not userid and username:
            recipient = self.getUserID(username)
        elif userid:
            recipient = userid
        else:
            raise Exception("Neither username nor userid provided.")
        if not recipient.isdigit():
            return print('Unable to use user id.')
        payload = {
          "recipient_users": f"[[{recipient}]]", 
          "action": "send_item",
          "is_shh_mode": "0",
          "send_attribution": "message_button",
          'client_context': random.randint(111111, 999999),
          "text": text,
          "device_id": self.device_id,
          "_uuid": self.uuid
        }
        return self.send('/direct_v2/threads/broadcast/text/', data=self.sign(payload))

    # Creats a new group message thread with the provided usernames / user IDs.
    # Usernames & user IDs can be present interchangably in users list.
    def createGroupMsgThread(self, text, users):
        for i, user in enumerate(users):
            if not user.isdigit():
                users[i] = self.getUserID(user)
        users = ','.join(users)
        payload = {
          "recipient_users": f"[[{users}]]", 
          "action": "send_item",
          "is_shh_mode": "0",
          "send_attribution": "inbox_new_message",
          'client_context': random.randint(111111, 999999),
          "text": text,
          "device_id": self.device_id,
          "_uuid": self.uuid
        }
        return self.send('/direct_v2/threads/broadcast/text/', data=self.sign(payload))

    # Sends any text to the provided thread(s).
    def sendText(self, text, threads):
        threads = ','.join(threads)
        payload = {'mentioned_user_ids': '[]',
         'action': 'send_item',
         'is_shh_mode': '0',
         'thread_ids': f"[{threads}]",
         'send_attribution': 'inbox',
         'client_context': random.randint(111111, 999999),
         'text': text,
         'device_id': self.device_id,
         '_uuid': self.uuid}
        return self.send(f'/direct_v2/threads/broadcast/text/', data=self.sign(payload))

    #doesnt work rn
    def sendVoice(self, path, threads):
        if self.VERBOSE: print("Sending voice msg")
        hreads = ','.join(threads)
        video_len = str(os.path.getsize(path))
        cv_video = cv2.VideoCapture(path)
        duration = cv_video.get(cv2.CAP_PROP_POS_MSEC)
        width = int(cv_video.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cv_video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        with open(path, 'rb') as video:
            upload_id = str(int(time.time() * 10000))
            upload_name = f"{random.randint(1111111111111111, 9999999999999999)}_0_-{video_len}"
            rupload_params = {
                "retry_context": '{"num_step_auto_retry":0,"num_reupload":0,"num_step_manual_retry":0}',
                "media_type": "11",
                "xsharing_user_ids": "[]",
                "upload_id": upload_id,
                "is_direct_voice": "1",
                "upload_media_duration_ms": str(int(duration)),
                "upload_media_width": str(width),
                "upload_media_height": str(height),
                "direct_v2": "1"
            }
            headers = {"X-Instagram-Rupload-Params": json.dumps(rupload_params), "X_FB_VIDEO_WATERFALL_ID": upload_id, "X-Entity-Type": "video/mp4"}
            if self.VERBOSE: print("Uploading")
            init_upload = self.s.get(f"https://i.instagram.com/rupload_igvideo/{upload_name}", headers=headers)
            if self.VERBOSE: print(f"Initialized status: {init_upload.json()}")
            headers.update({"Offset": "0", "X-Entity-Name": upload_name, "X-Entity-Length": video_len, "Content-Type": "application/octet-stream", "Content-Length": video_len})
            uploadvid = self.s.post(f"https://i.instagram.com/rupload_igvideo/{upload_name}", headers=headers, data=video) 
            if self.VERBOSE: print(f"Upload status: {uploadvid.json()}")
            data = {
             "action": "send_item",
             "thread_ids": f"[{threads}]",
             "waveform":"[0.5,0.6545084971874737,0.7938926261462366,0.9045084971874737,0.9755282581475768,1,0.9755282581475768,0.9045084971874737,0.7938926261462367,0.6545084971874737,0.5000000000000001,0.3454915028125264,0.2061073738537635,0.09549150281252633,0.024471741852423234,0,0.02447174185242318,0.09549150281252622,0.20610737385376332,0.34549150281252616]",
             "waveform_sampling_frequency_hz": "10",
             "client_context": random.randint(111111,999999),
             "device_id": self.device_id,
             "upload_id": upload_id,
             "video_result": "",
             "uuid": self.uuid}
            time.sleep(3)
            if self.VERBOSE: print(f"Sending")
            send_vid = self.s.post("https://i.instagram.com/api/v1/direct_v2/threads/broadcast/share_voice/", data=data)
            if self.VERBOSE: print(f"Send status: {send_vid}")
            if "Transcode error" in send_vid.text:
                print("Malformed video uploaded! Transcoding error..." )
                self.log(send_vid.text)
                return
            while True:
                if "Transcode not finished yet" in send_vid.text:
                    time.sleep(2)
                    send_vid = self.s.post("https://i.instagram.com/api/v1/direct_v2/threads/broadcast/share_voice/", data=data)
                else:
                    break
        # self.send(f'/direct_v2/threads/broadcast/share_voice/')

    def sendTextWithLink(self, text, links, threads):
        threads = ','.join(threads)
        links = ','.join([f'"{link}"' for link in links])
        print(links)
        payload = {'mentioned_user_ids': '[]',
         'action': 'send_item',
         'is_shh_mode': '0',
         'thread_ids': f"[{threads}]",
         'send_attribution': 'inbox',
         'client_context': random.randint(111111, 999999),
         'link_text': text,
         'link_urls': f'[{links}]',
         'device_id': self.device_id,
         '_uuid': self.uuid}
        return self.send(f'/direct_v2/threads/broadcast/link/', data=self.sign(payload))

    # Sends a user profile to the provided thread(s).
    def sendProfile(self, profile_id, threads):
        threads = ','.join(threads)
        payload = {'mentioned_user_ids': '[]',
         'action': 'send_item',
         'is_shh_mode': '0',
         'thread_ids': f"[{threads}]",
         'send_attribution': 'inbox',
         'client_context': random.randint(111111, 999999),
         'profile_user_id': profile_id,
         'device_id': self.device_id,
         '_uuid': self.uuid}
        return self.send(f'/direct_v2/threads/broadcast/profile/', data=self.sign(payload))

    # Sends a (verified) gif from a giphy id to the given thread(s).
    def sendGif(self, giphy_id, threads):
        threads = ','.join(threads)
        payload = {
         'is_shh_mode': '0',
         'thread_ids': f"[{threads}]",
         'send_attribution': 'direct_thread',
         'client_context': random.randint(111111, 999999),
         'id': giphy_id,
         'device_id': self.device_id,
         '_uuid': self.uuid}
        return self.send(f'/direct_v2/threads/broadcast/animated_media/', data=self.sign(payload))

    # Sends the photo (jpg only) at the provided path to the given thread(s).
    def sendPhoto(self, path, threads):
        threads = ','.join(threads)
        with open(path, 'rb') as photo:
            photo_len = str(os.path.getsize(path))
            upload_id = str(int(time.time() * 10000))       
            upload_name = f"{upload_id}_0_-{random.randint(111111111, 999999999)}"
            rupload_params = {
                "retry_context": '{"num_step_auto_retry":0,"num_reupload":0,"num_step_manual_retry":0}',
                "media_type": "1",
                "xsharing_user_ids": "[]",
                "upload_id": upload_id,
                "image_compression": '{"lib_name":"moz","lib_version":"3.1.m","quality":"0"}'
            }
            headers = {"X-Instagram-Rupload-Params": json.dumps(rupload_params), "X_FB_VIDEO_WATERFALL_ID": upload_id, "X-Entity-Type": "image/jpeg"}
            headers.update({"Offset": "0", "X-Entity-Name": upload_name, "X-Entity-Length": photo_len, "Content-Type": "application/octet-stream", "Content-Length": photo_len})
            uploadphoto = self.s.post(f"https://i.instagram.com/rupload_igphoto/{upload_name}", headers=headers, data=photo)   
            data = {"action": "send_item", "thread_ids": f"[{threads}]", "client_context": random.randint(111111, 999999), "device_id": self.device_id, "upload_id": upload_id, "uuid": self.uuid, "allow_full_aspect_ratio": "true"}
            return self.s.post("https://i.instagram.com/api/v1/direct_v2/threads/broadcast/configure_photo/", data=data)

    # Sends the video (mp4 only) at the provided path to the given thread(s).
    def sendVideo(self, path, threads):
        threads = ','.join(threads)
        video_len = str(os.path.getsize(path))
        cv_video = cv2.VideoCapture(path)
        duration = cv_video.get(cv2.CAP_PROP_POS_MSEC)
        width = int(cv_video.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cv_video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        with open(path, 'rb') as video:
            upload_id = str(int(time.time() * 10000))
            upload_name = f"{random.randint(1111111111111111, 9999999999999999)}_0_-{video_len}"
            rupload_params = {
                "retry_context": '{"num_step_auto_retry":0,"num_reupload":0,"num_step_manual_retry":0}',
                "media_type": "2",
                "xsharing_user_ids": "[]",
                "upload_id": upload_id,
                "upload_media_duration_ms": str(int(duration)),
                "upload_media_width": str(width),
                "upload_media_height": str(height),
                "direct_v2": "1"
            }           
            headers = {"X-Instagram-Rupload-Params": json.dumps(rupload_params), "X_FB_VIDEO_WATERFALL_ID": upload_id, "X-Entity-Type": "video/mp4"}
            init_upload = self.s.get(f"https://i.instagram.com/rupload_igvideo/{upload_name}", headers=headers)
            headers.update({"Offset": "0", "X-Entity-Name": upload_name, "X-Entity-Length": video_len, "Content-Type": "application/octet-stream", "Content-Length": video_len})
            uploadvid = self.s.post(f"https://i.instagram.com/rupload_igvideo/{upload_name}", headers=headers, data=video) 
            data = {"action": "send_item", "thread_ids": f"[{threads}]", "client_context": random.randint(111111, 999999), "device_id": self.device_id, "upload_id": upload_id, "video_result": "", "uuid": self.uuid}
            time.sleep(3)
            send_vid = self.s.post("https://i.instagram.com/api/v1/direct_v2/threads/broadcast/configure_video/", data=data)
            if "Transcode error" in send_vid.text:
                print("Malformed video uploaded! Transcoding error..." )
                self.log(send_vid.text)
                return
            while True:
                if "Transcode not finished yet" in send_vid.text:
                    time.sleep(2)
                    send_vid = self.s.post("https://i.instagram.com/api/v1/direct_v2/threads/broadcast/configure_video/", data=data)
                else:
                    break

    def updateMsgThreadName(self, thread, name):
        #there is something wrong with this endpoint and i cannot for the life of me figure out what so this is just gonna be broken for now.
        payload = {
            "_uuid": self.uuid,
            "title": name
        }
        return self.send(f'/direct_v2/threads/{thread}/update_title/', data=payload)

    # Returns the main user inbox as a dictionary.
    def getInbox(self, items_per_thread=1):
        return self.send(f'/direct_v2/inbox/?visual_message_return_type=unseen&thread_message_limit={items_per_thread}')

    # Returns the request user inbox (Message Requests) as a dictionary.
    def getRequestsInbox(self, items_per_thread=1):
        return self.send(f'/direct_v2/pending_inbox/?visual_message_return_type=unseen&thread_message_limit={items_per_thread}')

    def send(self, endpoint, data=None, login=False):
        if not login and not self.isLoggedIn and data:
            raise Exception('Not logged in.')
        self.s.headers.update({'Connection': 'close',
           'Accept': '*/*',
           'Content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
           'Cookie2': '$Version=1',
           'Accept-Language': 'en-US',
           'User-Agent': self.USER_AGENT})
        if data:
            if self.VERBOSE: print(f'posting to {self.API_BASE}{endpoint}')
            resp = self.s.post(f'{self.API_BASE}{endpoint}', data=data, verify=False)
        else:
            if self.VERBOSE: print(f'getting from {self.API_BASE}{endpoint}')
            resp = self.s.get(f'{self.API_BASE}{endpoint}')
        self.log(resp.text)
        self.LastResponse = resp
        if resp.status_code == 200:
            try:
                self.LastJson = resp.json()
                return resp.json()
            except json.decoder.JSONDecodeError:
                pass
        if resp.status_code == 429:
            self.log(resp.text)
            raise RateLimitError(f'Rate limited. See {self.LOGFILE} for details.')
        if resp.status_code != 200:
            print(str(resp.status_code)+'\n\n'+resp.text)
        return resp

    def log(self, text):
        if not self.LOGFILE:
            return print(f'No log file provided, API wants to log this message:\n\n{text}')
        else:
            with open(self.LOGFILE, 'w') as f:
                f.write(text)
            return

    def generateUUID(self, dashed=True):
        generated_uuid = str(uuid.uuid4())
        if dashed:
            return generated_uuid
        else:
            return generated_uuid.replace('-', '')

    def getUserID(self, username):
        url = f"https://www.instagram.com/{username}/?__a=1"
        if username.lower() in self._getCache()['ids']:
            return self._getCache()['ids'][username.lower()]
        response = self.s.get(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
      
        try:
            respJSON = response.json()
        except json.decoder.JSONDecodeError:
            with open('debug.json', 'w+') as f:
                f.write(f'{response}\n\n{response.text}')
            return self.getUserIDsecondary(username)
        try:
            user_id = str( respJSON['graphql']['user']['id'] )
            cache = self._getCache()
            cache['ids'][username.lower()] = user_id
            self._writeCache(cache)
            return user_id
        except KeyError:
            with open('debug.json', 'w+') as f:
                f.write(f'{response}\n\n{response.text}')
            return self.getUserIDsecondary(username)

    def getUserIDsecondary(self, username):
        response = self.s.get("https://www.instagram.com/web/search/topsearch/?context=blended&query="+username+"&rank_token=0.3953592318270893&count=1")
      
        try:
            respJSON = response.json()
        except json.decoder.JSONDecodeError:
            with open('debug.json', 'w+') as f:
                f.write(f'{response}\n\n{response.text}')
        try:
            user_id = str( respJSON['users'][0].get("user").get("pk") )
            cache = self._getCache()
            cache['ids'][username.lower()] = user_id
            self._writeCache(cache)
            return user_id
        except KeyError:
            print('UNABLE TO GET USERID USING BOTH PRIMARY AND SECONDARY METHODS!')
            return "Unexpected error"

    def downloadProfilePicture(self, username, path):
        pfp = self.s.get(self.getUserInfo(username)['profile_pic_url_hd'])
        with open(path, 'wb') as f:
            f.write(pfp.content)
        return path

    def getUserInfo(self, username):
        resp = self.s.get(f'https://instagram.com/{username}/?__a=1')
        try:
            return resp.json()['graphql']['user']
        except KeyError:
            raise InvalidDataError('Invalid username.')

    def generateDeviceID(self, seed):
        volatile_seed = "12345"
        m = hashlib.md5()
        m.update(seed.encode('utf-8') + volatile_seed.encode('utf-8'))
        return 'android-' + m.hexdigest()[:16]

    def sign(self, data, skip_quote=False):
        data = json.dumps(data)
        if not skip_quote:
            try:
                parsedData = urllib.parse.quote(data)
            except AttributeError:
                parsedData = urllib.parse.quote(data)
        else:
            parsedData = data
        return 'ig_sig_key_version=' + self.SIG_KEY_VERSION + '&signed_body=' + hmac.new(self.IG_SIG_KEY.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest() + '.' + parsedData
