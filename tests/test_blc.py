import importlib.machinery
import importlib.util
import io
import json
import os
import struct
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader("blc", os.path.join(HERE, "..", "blc"))
spec = importlib.util.spec_from_loader("blc", loader)
blc = importlib.util.module_from_spec(spec)
loader.exec_module(blc)

COMMENT = "Need to watch the conference talk a client sent me for the proposal"


def at(hhmm):
    """Unix time for today at HH:MM local time."""
    today = time.localtime()
    hours, minutes = map(int, hhmm.split(":"))
    return time.mktime((today.tm_year, today.tm_mon, today.tm_mday, hours, minutes, 0, 0, 0, -1))


def config(rules=(), pauses=()):
    return {"rules": list(rules), "pauses": list(pauses)}


def rule(domain, start="00:00", end="24:00"):
    return {"domain": domain, "start": start, "end": end}


class ParsingTests(unittest.TestCase):
    def test_domains(self):
        self.assertEqual(blc.normalize_domain("*.YouTube.com."), "youtube.com")
        self.assertEqual(blc.normalize_domain("music.youtube.com"), "music.youtube.com")
        for bad in ["youtube", "../etc/hosts", "you tube.com", "-x.com", "*.", "", "x.c"]:
            with self.assertRaises(blc.UserError, msg=bad):
                blc.normalize_domain(bad)

    def test_clock(self):
        self.assertEqual(blc.parse_clock("00:00"), 0)
        self.assertEqual(blc.parse_clock("7:05"), 425)
        self.assertEqual(blc.parse_clock("19:00"), 1140)
        self.assertEqual(blc.parse_clock("24:00"), 1440)
        for bad in ["24:01", "25:00", "12:60", "noon", "1900"]:
            with self.assertRaises(blc.UserError, msg=bad):
                blc.parse_clock(bad)

    def test_duration(self):
        self.assertEqual(blc.parse_duration("30min"), 1800)
        self.assertEqual(blc.parse_duration("30m"), 1800)
        self.assertEqual(blc.parse_duration("30"), 1800)
        self.assertEqual(blc.parse_duration("1h"), 3600)
        self.assertEqual(blc.parse_duration("1h30m"), 5400)
        self.assertEqual(blc.parse_duration("2h"), 7200)
        for bad in ["3h", "0m", "abc", "", "h"]:
            with self.assertRaises(blc.UserError, msg=bad):
                blc.parse_duration(bad)

    def test_comment(self):
        self.assertGreaterEqual(len(COMMENT), blc.MIN_COMMENT)
        self.assertEqual(blc.require_comment(COMMENT.split()), COMMENT)
        with self.assertRaises(blc.UserError):
            blc.require_comment(["x" * 49])
        with self.assertRaises(blc.UserError):
            blc.require_comment(["   " + "x" * 30 + "   ", "  "])


class ScheduleTests(unittest.TestCase):
    def test_windows(self):
        day = (blc.parse_clock("00:00"), blc.parse_clock("19:00"))
        self.assertTrue(blc.in_window(*day, 0))
        self.assertTrue(blc.in_window(*day, 1139))
        self.assertFalse(blc.in_window(*day, 1140))
        night = (blc.parse_clock("22:00"), blc.parse_clock("07:00"))
        self.assertTrue(blc.in_window(*night, 23 * 60))
        self.assertTrue(blc.in_window(*night, 6 * 60))
        self.assertFalse(blc.in_window(*night, 12 * 60))
        self.assertTrue(blc.in_window(*blc.ALL_DAY, 1439))

    def test_blocked_now(self):
        cfg = config([rule("youtube.com", "00:00", "19:00"), rule("x.com", "22:00", "07:00"), rule("reddit.com")])
        self.assertEqual(blc.blocked_now(cfg, at("10:00")), {"youtube.com", "reddit.com"})
        self.assertEqual(blc.blocked_now(cfg, at("23:00")), {"x.com", "reddit.com"})

    def test_pauses(self):
        now = at("10:00")
        cfg = config(
            [rule("youtube.com"), rule("reddit.com")],
            [{"domain": "youtube.com", "until": now + 60}, {"domain": "reddit.com", "until": now - 60}],
        )
        self.assertEqual(blc.blocked_now(cfg, now), {"reddit.com"})

    def test_malformed_entries_are_skipped(self):
        cfg = config(
            [rule("youtube.com"), {"domain": "../../etc/sudoers", "start": "00:00", "end": "24:00"}, {"domain": 5}, "x"],
            [{"domain": "youtube.com", "until": "soon"}, None],
        )
        self.assertEqual(blc.blocked_now(cfg, at("10:00")), {"youtube.com"})


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (blc.CONFIG_PATH, blc.LOG_PATH, blc.RESOLVER_DIR, blc.daemon_running)
        blc.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        blc.LOG_PATH = os.path.join(self.tmp.name, "log")
        blc.RESOLVER_DIR = os.path.join(self.tmp.name, "resolver")
        blc.daemon_running = lambda: True

    def tearDown(self):
        blc.CONFIG_PATH, blc.LOG_PATH, blc.RESOLVER_DIR, blc.daemon_running = self.saved
        self.tmp.cleanup()

    def run_blc(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = blc.main(list(argv))
        return code, out.getvalue()

    def config(self):
        with open(blc.CONFIG_PATH) as f:
            return json.load(f)

    def test_block_pause_resume_unblock(self):
        self.assertEqual(self.run_blc("block", "*.youtube.com")[0], 0)
        self.assertEqual(self.config()["rules"], [rule("youtube.com")])
        self.assertIn("youtube.com", blc.blocked_now(self.config()))

        code, out = self.run_blc("pause", "youtube.com", "30min", "too short")
        self.assertEqual(code, 1)
        self.assertIn("50 characters", out)

        self.assertEqual(self.run_blc("pause", "youtube.com", "30min", COMMENT)[0], 0)
        self.assertNotIn("youtube.com", blc.blocked_now(self.config()))
        self.assertIn("paused until", self.run_blc("status")[1])

        self.assertEqual(self.run_blc("resume", "youtube.com")[0], 0)
        self.assertIn("youtube.com", blc.blocked_now(self.config()))

        self.assertEqual(self.run_blc("unblock", "youtube.com")[0], 1)
        self.assertEqual(self.run_blc("unblock", "youtube.com", *COMMENT.split())[0], 0)
        self.assertEqual(self.config(), config())

        with open(blc.LOG_PATH) as f:
            actions = [line.split("\t")[1] for line in f]
        self.assertEqual(actions, ["block", "pause", "resume", "unblock"])
        self.assertIn(COMMENT, self.run_blc("log")[1])

    def test_block_windows(self):
        self.assertEqual(self.run_blc("block", "x.com", "22:00", "7:00")[0], 0)
        self.assertEqual(self.run_blc("block", "x.com", "12:00", "13:00")[0], 0)
        self.assertIn("already blocked", self.run_blc("block", "x.com", "22:00", "07:00")[1])
        self.assertEqual(len(self.config()["rules"]), 2)
        self.assertIn("22:00-07:00, 12:00-13:00", self.run_blc("status")[1])
        self.assertEqual(self.run_blc("block", "x.com", "22:00")[0], 1)
        self.assertEqual(self.run_blc("block", "x.com", "10:00", "10:00")[0], 1)

    def test_pause_needs_a_rule(self):
        code, out = self.run_blc("pause", "youtube.com", "30min", COMMENT)
        self.assertEqual(code, 1)
        self.assertIn("isn't blocked", out)

    def test_status_warns_when_daemon_is_down(self):
        self.run_blc("block", "youtube.com")
        blc.daemon_running = lambda: False
        self.assertIn("isn't running", self.run_blc("status")[1])


class DaemonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmp.name, "config.json")
        self.resolver = os.path.join(self.tmp.name, "resolver")
        self.saved_flush = blc.flush_dns
        self.flushes = 0
        blc.flush_dns = self.count_flush
        self.daemon = blc.Daemon(self.config_path, self.resolver)
        self.messages = []
        self.daemon.say = self.messages.append

    def tearDown(self):
        blc.flush_dns = self.saved_flush
        self.tmp.cleanup()

    def count_flush(self):
        self.flushes += 1

    def write(self, text):
        with open(self.config_path, "w") as f:
            f.write(text)

    def test_sync_follows_schedule(self):
        self.write(json.dumps(config([rule("youtube.com", "00:00", "19:00")])))
        self.daemon.sync(now=at("10:00"))
        with open(os.path.join(self.resolver, "youtube.com")) as f:
            self.assertEqual(f.read(), "# managed by blc\nnameserver 127.0.0.1\nport 54\n")
        self.assertEqual(self.flushes, 1)

        self.daemon.sync(now=at("10:00"))
        self.assertEqual(self.flushes, 1)

        self.daemon.sync(now=at("20:00"))
        self.assertEqual(os.listdir(self.resolver), [])
        self.assertEqual(self.flushes, 2)

    def test_foreign_files_are_left_alone(self):
        os.makedirs(self.resolver)
        with open(os.path.join(self.resolver, "test"), "w") as f:
            f.write("nameserver 127.0.0.1\n")
        with open(os.path.join(self.resolver, "youtube.com"), "w") as f:
            f.write("nameserver 10.0.0.1\n")
        self.write(json.dumps(config([rule("youtube.com")])))
        self.daemon.sync()
        self.daemon.sync()
        self.assertEqual(sorted(os.listdir(self.resolver)), ["test", "youtube.com"])
        self.assertEqual(len([m for m in self.messages if "can't block" in m]), 1)

    def test_broken_config_keeps_blocks(self):
        self.write(json.dumps(config([rule("youtube.com")])))
        self.daemon.sync()
        self.write("{not json")
        self.daemon.sync()
        self.daemon.sync()
        self.assertEqual(os.listdir(self.resolver), ["youtube.com"])
        self.assertEqual(len([m for m in self.messages if "keeping current blocks" in m]), 1)

    def test_symlinked_config_is_refused(self):
        os.symlink("/etc/hosts", self.config_path)
        with self.assertRaises(OSError):
            blc.read_config(self.config_path)


class ResponderTests(unittest.TestCase):
    def test_nxdomain_reply(self):
        query = blc.build_query("www.youtube.com", qid=0xBEEF)
        reply = blc.nxdomain_reply(query)
        qid, flags, qd, an, ns, ar = struct.unpack(">HHHHHH", reply[:12])
        self.assertEqual(qid, 0xBEEF)
        self.assertTrue(flags & 0x8000)  # response
        self.assertTrue(flags & 0x0100)  # recursion desired, copied
        self.assertEqual(flags & 0xF, 3)  # NXDOMAIN
        self.assertEqual((qd, an, ns, ar), (1, 0, 0, 0))
        self.assertEqual(reply[12:], query[12:])

    def test_ignores_non_queries(self):
        self.assertIsNone(blc.nxdomain_reply(b"short"))
        reply = blc.nxdomain_reply(blc.build_query("youtube.com"))
        self.assertIsNone(blc.nxdomain_reply(reply))
        self.assertIsNone(blc.nxdomain_reply(blc.build_query("youtube.com")[:-3]))


if __name__ == "__main__":
    unittest.main()
