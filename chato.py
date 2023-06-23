#!/usr/bin/env python3
import argparse
import asyncio
import json
import subprocess
import time
from http.cookies import SimpleCookie
from pathlib import Path

import yaml
from aiohttp import ClientSession
from miservice import MiAccount, MiNAService
from requests.utils import cookiejar_from_dict
from rich import print

LATEST_ASK_API = "https://userprofile.mina.mi.com/device_profile/v2/conversation?source=dialogu&hardware={hardware}&timestamp={timestamp}&limit=2"
COOKIE_TEMPLATE = "deviceId={device_id}; serviceToken={service_token}; userId={user_id}"

HARDWARE_COMMAND_DICT = {
    "LX06": "5-1",
    "L05B": "5-3",
    "S12A": "5-1",
    "LX01": "5-1",
    "L06A": "5-1",
    "LX04": "5-1",
    "L05C": "5-3",
    "L17A": "7-3",
    "X08E": "7-3",
    # add more here
}


### HELP FUNCTION ###
def parse_cookie_string(cookie_string):
    cookie = SimpleCookie()
    cookie.load(cookie_string)
    cookies_dict = {}
    cookiejar = None
    for k, m in cookie.items():
        cookies_dict[k] = m.value
        cookiejar = cookiejar_from_dict(cookies_dict, cookiejar=None, overwrite=True)
    return cookiejar


class ChatoAI:
    def __init__(
            self,
            use_command=False,
            verbose=False,
    ):
        with open('config.yml', 'r') as f:
            config = yaml.safe_load(f)
            self.hardware = config['HARDWARE']
            self.mi_user = config['MI_USER']
            self.mi_pass = config['MI_PASS']
            self.chato_api = config['CHATO_API']

        self.mi_token_home = Path.home() / ".mi.token"
        self.cookie_string = ""
        self.cookie = None
        self.last_timestamp = 0  # timestamp last call mi speaker
        self.session = None
        self.user_id = ""
        self.device_id = ""
        self.service_token = ""
        self.use_command = use_command
        self.tts_command = HARDWARE_COMMAND_DICT.get(self.hardware, "5-1")
        self.conversation_id = None
        self.parent_id = None
        self.miboy_account = None
        self.mina_service = None
        self.verbose = verbose

    async def init_all_data(self, session):
        await self.login_miboy(session)
        await self._init_data_hardware()
        with open(self.mi_token_home) as f:
            user_data = json.loads(f.read())
        self.user_id = user_data.get("userId")
        self.service_token = user_data.get("micoapi")[1]
        self._init_cookie()

    async def login_miboy(self, session):
        self.session = session
        self.account = MiAccount(
            session,
            self.mi_user,
            self.mi_pass,
            str(self.mi_token_home),
        )
        # Forced login to refresh to refresh token
        await self.account.login("micoapi")
        self.mina_service = MiNAService(self.account)

    async def _init_data_hardware(self):
        hardware_data = await self.mina_service.device_list()
        for h in hardware_data:
            if h.get("hardware", "") == self.hardware:
                self.device_id = h.get("deviceID")
                break
        else:
            raise Exception(f"we have no hardware: {self.hardware} please check")

    def _init_cookie(self):
        self.cookie_string = COOKIE_TEMPLATE.format(
            device_id=self.device_id,
            service_token=self.service_token,
            user_id=self.user_id,
        )
        self.cookie = parse_cookie_string(self.cookie_string)

    async def simulate_xiaoai_question(self):
        data = {
            "code": 0,
            "message": "Success",
            "data": '{"bitSet":[0,1,1],"records":[{"bitSet":[0,1,1,1,1],"answers":[{"bitSet":[0,1,1,1],"type":"TTS","tts":{"bitSet":[0,1],"text":"Fake Answer"}}],"time":1677851434593,"query":"Fake Question","requestId":"fada34f8fa0c3f408ee6761ec7391d85"}],"nextEndTime":1677849207387}',
        }
        # Convert the data['data'] value from a string to a dictionary
        data_dict = json.loads(data["data"])
        # Get the first item in the records list
        record = data_dict["records"][0]
        # Replace the query and time values with user input
        record["query"] = input("Enter the new query: ")
        record["time"] = int(time.time() * 1000)
        # Convert the updated data_dict back to a string and update the data['data'] value
        data["data"] = json.dumps(data_dict)
        await asyncio.sleep(1)
        return data

    async def get_latest_ask_from_xiaoai(self):
        r = await self.session.get(
            LATEST_ASK_API.format(
                hardware=self.hardware, timestamp=str(int(time.time() * 1000))
            ),
            cookies=parse_cookie_string(self.cookie),
        )
        return await r.json()

    def get_last_timestamp_and_record(self, data):
        if d := data.get("data"):
            records = json.loads(d).get("records")
            if not records:
                return 0, None
            last_record = records[0]
            timestamp = last_record.get("time")
            return timestamp, last_record

    async def do_tts(self, value):
        if not self.use_command:
            try:
                await self.mina_service.text_to_speech(self.device_id, self._normalize(value))
            except Exception as e:
                # print(e)
                # do nothing is ok
                pass
        else:
            subprocess.check_output(["micli", self.tts_command, value])

    def _normalize(self, message):
        message = message.replace(" ", "--")
        message = message.replace("\n", "，")
        message = message.replace('"', "，")
        return message

    async def chato_chat(self, query, session):
        payload = {
            "p": query
        }
        response = await session.post(f'{self.chato_api}', json=payload)
        return await response.json()

    async def get_if_xiaoai_is_playing(self):
        playing_info = await self.mina_service.player_get_status(self.device_id)
        # WTF xiaomi api
        is_playing = (
                json.loads(playing_info.get("data", {}).get("info", "{}")).get("status", -1)
                == 1
        )
        return is_playing

    async def stop_if_xiaoai_is_playing(self):
        is_playing = await self.get_if_xiaoai_is_playing()
        if is_playing:
            # stop it
            await self.mina_service.player_pause(self.device_id)

    async def run_forever(self):
        print("现在开始向小爱同学提问吧...\n")
        async with ClientSession() as session:
            await self.init_all_data(session)
            while 1:
                if self.verbose:
                    print(
                        f"Now listening xiaoai new message timestamp: {self.last_timestamp}"
                    )
                try:
                    r = await self.get_latest_ask_from_xiaoai()
                except Exception:
                    # we try to init all again
                    await self.init_all_data(session)
                    r = await self.get_latest_ask_from_xiaoai()

                new_timestamp, last_record = self.get_last_timestamp_and_record(r)
                if new_timestamp > self.last_timestamp and int(time.time()) * 1000 - int(new_timestamp) < 5000:
                    self.last_timestamp = new_timestamp
                    query = last_record.get("query", "")
                    print(f"小爱同学： {query}")
                    # 阻止小爱同学说话
                    await self.stop_if_xiaoai_is_playing()
                    try:
                        print(
                            "以下是小爱的回答: ",
                            last_record.get("answers")[0]
                            .get("tts", {})
                            .get("text"),
                        )
                    except:
                        print("小爱没回")

                    try:
                        chato_response = await self.chato_chat(query, session)
                        print(f"chato 正在进行回答 {chato_response}")
                        await self.do_tts(chato_response.get("data").get("content"))
                    except:
                        await self.do_tts("chato服务异常")
                else:
                    if self.verbose:
                        print("No new xiao ai record")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--use_command",
        dest="use_command",
        action="store_true",
        help="use command to tts",
    )
    parser.add_argument(
        "--verbose",
        dest="verbose",
        action="store_true",
        help="show info",
    )
    options = parser.parse_args()

    # if set
    miboy = ChatoAI(
        options.use_command,
        options.verbose,
    )
    asyncio.run(miboy.run_forever())
