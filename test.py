# -*- coding=utf-8 -*-
from automator.FTTAutomator import FTTTestCase, get_device
FTTDevice = get_device()
index_page = u'首页.yaml'


@FTTTestCase
class TestCase(object):
    def __init__(self):
        FTTTestCase.super(TestCase, self).__init__()
        self.package = "com.iqiyi.ivrcinema.cb"

    def setup(self):
        # start app
        start_cmd = "shell monkey -p {0} -c {1} 1".format(self.package, "android.intent.category.LAUNCHER")
        FTTDevice.adb.cmd(*start_cmd.split(" ")).communicate()
        # swith ui page
        FTTDevice.source = index_page
        # click ftt-selector
        FTTDevice.click_selector(name='my_tab')

    def cleanup(self):
        # close app
        close_cmd = "shell am force-stop {}".format(self.package)
        FTTDevice.adb.cmd(*close_cmd.split(" ")).communicate()


if __name__ == "__main__":
    TestCase()
