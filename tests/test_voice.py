#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语音批准的回归测试。

分两层：
  1. ParseTests   —— 纯函数：一句话怎么变成 approve / reject / 不认。
  2. HttpTests    —— 接口：默认关闭、口令不对不动任务、批准走同一条路径。

这里刻意把「不批准」写进用例 —— 它包含「批准」两个字，
否定判断一旦写反，就会变成一次误批准。
"""
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from codexglasses import voice
from codexglasses.server import Bridge


class ParseTests(unittest.TestCase):
    def test_approve_phrases(self):
        for text in ["批准", "确认批准", "批准执行", "我批准了", "Approve", "approved!", "同意执行，批准"]:
            self.assertEqual(voice.parse(text), "approve", text)

    def test_reject_wins_over_approve(self):
        # 这些句子里都含「批准」，必须先判否定
        for text in ["不批准", "别批准", "不要批准", "取消批准", "拒绝", "reject", "denied"]:
            self.assertEqual(voice.parse(text), "reject", text)

    def test_unknown_is_none(self):
        for text in ["", "   ", "嗯", "等一下", "再说吧", "这个任务看起来还行"]:
            self.assertIsNone(voice.parse(text), text)

    def test_non_string_and_oversized(self):
        self.assertIsNone(voice.parse(None))
        self.assertIsNone(voice.parse(123))
        self.assertIsNone(voice.parse(["批准"]))
        # 过长多半是串了别的话，一律不认
        self.assertIsNone(voice.parse("批准" + "啊" * 200))

    def test_punctuation_and_spacing(self):
        self.assertEqual(voice.parse(" 批 准 。"), "approve")
        self.assertEqual(voice.parse("不 批 准！"), "reject")

    def test_matched_phrase_only_records_phrase(self):
        # 审计只记短语，不记整段话
        self.assertEqual(voice.matched_phrase("我说了一下，确认批准这个任务"), "确认批准")
        self.assertIsNone(voice.matched_phrase("随便聊聊"))


class VoiceEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.project = self.path / "project"
        self.project.mkdir()
        (self.project / "hello.py").write_text("print('hi')")
        self.bridge = Bridge(self.path / "state",
                             {"projects": {"demo": {"path": str(self.project), "allow_write": False}}},
                             simulate=True)
        self.device, self.token = self.bridge.store.add_device("phone")
        _, self.operator = self.bridge.store.add_device("desktop", "operator")
        self.client = TestClient(TestServer(self.bridge.app(test_insecure=True)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    def headers(self, operator=True):
        return {"Authorization": "Bearer " + (self.operator if operator else self.token)}

    async def new_task(self):
        r = await self.client.post("/v1/tasks", headers=self.headers(False), json={
            "v": 1, "request_id": "voice_test_001", "project": "demo",
            "action": "inspect", "prompt": "check code"})
        self.assertEqual(r.status, 201)
        return await r.json()

    async def voice(self, task_id, transcript, ack=True):
        return await self.client.post(f"/v1/operator/tasks/{task_id}/voice-decision",
                                      headers=self.headers(), json={
                                          "transcript": transcript,
                                          "acknowledge_snapshot_and_provider": ack})

    async def test_disabled_by_default(self):
        task = await self.new_task()
        r = await self.voice(task["id"], "批准")
        self.assertEqual(r.status, 400)
        self.assertEqual((await r.json())["error"], "voice_approval_disabled")
        self.assertEqual(self.bridge.store.task(task["id"])["status"], "pending")

    async def test_unrecognized_keeps_task_pending(self):
        self.bridge.config["allow_voice_approval"] = True
        task = await self.new_task()
        r = await self.voice(task["id"], "嗯，我想想")
        self.assertEqual(r.status, 400)
        self.assertEqual((await r.json())["error"], "voice_not_recognized")
        self.assertEqual(self.bridge.store.task(task["id"])["status"], "pending")

    async def test_approve_by_voice(self):
        self.bridge.config["allow_voice_approval"] = True
        task = await self.new_task()
        r = await self.voice(task["id"], "确认批准")
        self.assertEqual(r.status, 200)
        self.assertIn(self.bridge.store.task(task["id"])["status"],
                      {"preparing", "running", "completed"})

    async def test_reject_by_voice(self):
        self.bridge.config["allow_voice_approval"] = True
        task = await self.new_task()
        r = await self.voice(task["id"], "不批准")
        self.assertEqual(r.status, 200)
        self.assertEqual(self.bridge.store.task(task["id"])["status"], "rejected")

    async def test_still_requires_acknowledgement(self):
        self.bridge.config["allow_voice_approval"] = True
        task = await self.new_task()
        r = await self.voice(task["id"], "批准", ack=False)
        self.assertEqual(r.status, 400)
        self.assertEqual(self.bridge.store.task(task["id"])["status"], "pending")

    async def test_second_voice_decision_is_refused(self):
        self.bridge.config["allow_voice_approval"] = True
        task = await self.new_task()
        self.assertEqual((await self.voice(task["id"], "不批准")).status, 200)
        r = await self.voice(task["id"], "批准")
        self.assertEqual(r.status, 400)
        self.assertEqual(self.bridge.store.task(task["id"])["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
