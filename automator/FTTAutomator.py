# -*- coding: UTF-8 -*-
'''
Created on 20170315 by leochechen
@Summary: ftt-automator 基于uiautomator的二次封装
'''
import os
import re
import time
import itertools
import threading
from functools import wraps
from time import sleep
from libs import yaml
from UiAutomator import point, rect, param_to_property, DEVICE_PORT, next_local_port
from UiAutomator import Adb, AutomatorServer, AutomatorDevice

try:
    import urllib2
except ImportError:
    import urllib.request as urllib2
try:
    from httplib import HTTPException
except:
    from http.client import HTTPException
try:
    if os.name == 'nt':
        from libs import urllib3
except:  # to fix python setup error on Windows.
    pass


class FTTJob(threading.Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}, verbose=None, interval=1, times=-1):
        super(FTTJob, self).__init__(name=name)
        self.__name = name
        self.__target = target
        self.__args = args
        self.__kwargs = kwargs
        self.__interval = interval
        self.__times = times
        # 用于暂停线程的标识
        self.__flag = threading.Event()
        # 设置为True
        self.__flag.set()
        # 用于停止线程的标识
        self.__running = threading.Event()
        # 将running设置为True
        self.__running.set()

    def _control(self):
        if self.__target and self.__times > 0:
            self.__target(*self.__args, **self.__kwargs)
            self.__times -= 1
            if self.__times == 0:
                self.stop()
        elif self.__target and self.__times == -1:
            # print "invoke {}".format(self.name)
            self.__target(*self.__args, **self.__kwargs)
        else:
            raise EnvironmentError("target and times doesn't meet the conditions")

        time.sleep(self.__interval)

    def run(self):
        while self.__running.isSet():
            self.__flag.wait()
            self._control()

    def pause(self):
        self.__flag.clear()

    def resume(self):
        self.__flag.set()

    def stop(self):
        self.__flag.set()
        self.__running.clear()

    def __str__(self):
        return "<FTTJob-{} interval={} times={}>".format(self.__name, self.__interval, self.__times)

    def __repr__(self):
        return self.__str__()


class FTTTestCase(object):
    '''
    @FttTestCase
    class TestCase(object):
        def __init__(self):
            pass

        def setup(self):
            pass

        def tearDown(self):
            pass
    '''
    @property
    def cls_name(self):
        return self.cls.__name__

    @staticmethod
    def super(ftttestcase_cls, instance):
        '''
        返回父类对象
        :param ftttestcase_cls: 被FTTTestCase修饰的类
        :param instance: self
        :return:
        '''
        if hasattr(ftttestcase_cls, 'cls'):
            return super(ftttestcase_cls.cls, instance)
        else:
            raise TypeError("{} hasn't cls property".format(ftttestcase_cls))

    @staticmethod
    def inherit(ftttestcase_cls):
        '''
        从ftttestcase实例中提取类实例
        :param ftttestcase_cls: 被FTTTestCase修饰的类
        :return: 原始类
        '''
        if type(ftttestcase_cls) is not FTTTestCase:
            raise EnvironmentError("只接受@FTTTestCase修饰过的类")
        return ftttestcase_cls.cls

    def __init__(self, cls):
        self.cls = cls

    def __call__(self, custom_module=None):
        ins = self.cls()
        if hasattr(ins, 'setup'):
            ins.setup()
        else:
            raise EnvironmentError("ftt testcase class hasn't setup method...")

        if hasattr(ins, 'cleanup'):
            ins.cleanup()
        else:
            raise EnvironmentError("ftt testcase class hasn't cleanup method...")

    def __getattr__(self, item):
        return getattr(self.cls, item)

    def __str__(self):
        return "<{0} instance-{1}>".format(self.__class__.__name__, self.cls.__name__)

    def __repr__(self):
        return self.__str__()


class FTTUISelector(object):
    # 将yaml格式语法数据提取出来，形成AutomatorDeviceObject
    __fields = (
        'text',
        'textContains',
        'textMatches',
        'textStartsWith',
        'className',
        'classNameMatches',
        'description',
        'descriptionContains',
        'descriptionMatches',
        'descriptionStartsWith',
        'checkable',
        'checked',
        'clickable',
        'longClickable',
        'scrollable',
        'enabled',
        'focusable',
        'focused',
        'selected',
        'packageName',
        'packageNameMatches',
        'resourceId',
        'resourceIdMatches',
        'index',
        'instance'
    )

    def __init__(self, device):
        self.ftt_device = device
        self._steams = {}
        self._path = None
        self._steam = None

    @property
    def path(self):
        return self._path.encode('utf-8') if type(self._path) is unicode else self._path

    @property
    def steam(self):
        return self._steam

    def load(self, path):
        self._steam = self._steams[path] if path in self._steams else yaml.load(open(path))
        self._path = path

    def _get_selector(self, name):
        '''
        根据yaml数据文件中的name关键字或者selector
        :param name: 关键字
        :return:
        '''
        try:
            return self._get_selector_instance(None, self._steam[name])
        except TypeError:
            raise EnvironmentError("配置Selector UI的页面路径")

    def _get_selector_instance(self, instance, data):
        '''
        获取selector实例
        :param instance: 当前的selector实例
        :param data: 用例定位的数据
        :return:
        '''

        selector = dict([(item, data[item]) for item in data.keys() if item in self.__fields])
        if 'method' not in data:
            crt_instance = self.ftt_device(**selector)
        elif data['method'] == 'child_by_text':
            '''
            method: child_by_text
            txt: your child text
            ui selecotor
            '''
            crt_instance = instance.child_by_text(data['txt'], **selector)
        elif data['method'] == 'child_by_instance':
            '''
            method: child_by_instance
            instance: your instance
            ui selecotor
            '''
            crt_instance = instance.child_by_instance(int(data['instance']), **selector)
        elif data['method'] == 'child_by_description':
            '''
            method: child_by_description
            txt: your child text
            ui selecotor
            '''
            crt_instance = instance.child_by_instance(int(data['txt']), **selector)
        else:
            crt_instance = eval('.'.join(['instance', data['method']]))(**selector)

        if 'extand' not in data:
            return crt_instance
        else:
            return self._get_selector_instance(crt_instance, data['extand'])

    def __call__(self, name):
        return self._get_selector(name)


class FTTAdb(Adb):
    def __init__(self, serial=None, adb_server_host=None, adb_server_port=None):
        super(FTTAdb, self).__init__(serial=serial, adb_server_host=adb_server_host, adb_server_port=adb_server_port)
        self.__adb_cmd = None

    def adb(self):
        if self.__adb_cmd is None:
            '''
            if "ANDROID_HOME" in os.environ:
                filename = "adb.exe" if os.name == 'nt' else "adb"
                adb_cmd = os.path.join(os.environ["ANDROID_HOME"], "platform-tools", filename)
                if not os.path.exists(adb_cmd):
                    raise EnvironmentError(
                        "Adb not found in $ANDROID_HOME path: %s." % os.environ["ANDROID_HOME"])
            else:
                import distutils
                if "spawn" not in dir(distutils):
                    import distutils.spawn
                adb_cmd = distutils.spawn.find_executable("adb")
                if adb_cmd:
                    adb_cmd = os.path.realpath(adb_cmd)
                else:
                    raise EnvironmentError("$ANDROID_HOME environment not set.")
            self.__adb_cmd = adb_cmd
            '''
            # @Modified by leochechen on 20171221.
            # use the specified adb on nt system
            filename = "adb.exe" if os.name == 'nt' else "adb"
            self.__adb_cmd = os.path.join(os.path.dirname(__file__), "../adb", filename)
        return self.__adb_cmd


class FTTAutomatorServer(AutomatorServer):
    __jar_files = {
        "bundle.jar": "libs/bundle.jar",
        "uiautomator-stub.jar": "libs/uiautomator-stub.jar"
    }

    __apk_files = ["libs/app-uiautomator.apk", "libs/app-uiautomator-test.apk"]

    __sdk = 0

    def __init__(self, serial=None, local_port=None, device_port=None, adb_server_host=None, adb_server_port=None):
        self.uiautomator_process = None
        self.adb = FTTAdb(serial=serial, adb_server_host=adb_server_host, adb_server_port=adb_server_port)
        self.device_port = int(device_port) if device_port else DEVICE_PORT
        if local_port:
            self.local_port = local_port
        else:
            try:  # first we will try to use the local port already adb forwarded
                for s, lp, rp in self.adb.forward_list():
                    if s == self.adb.device_serial() and rp == 'tcp:%d' % self.device_port:
                        self.local_port = int(lp[4:])
                        break
                else:
                    self.local_port = next_local_port(adb_server_host)
            except:
                self.local_port = next_local_port(adb_server_host)

    def push(self):
        base_dir = os.path.dirname(__file__)
        for jar, url in self.__jar_files.items():
            filename = os.path.join(base_dir, "..", url)
            self.adb.cmd("push", filename, "/data/local/tmp/").wait()
        return list(self.__jar_files.keys())

    def install(self):
        base_dir = os.path.dirname(__file__)
        for apk in self.__apk_files:
            self.adb.cmd("install", "-r -t", os.path.join(base_dir, "..", apk)).wait()

    def start(self, timeout=5):
        # print "in FTTAutomatorServer start"
        if self.sdk_version() < 18:
            files = self.push()
            cmd = list(itertools.chain(
                ["shell", "uiautomator", "runtest"],
                files,
                ["-c", "com.github.uiautomatorstub.Stub"]
            ))
        else:
            self.install()
            cmd = ["shell", "am", "instrument", "-w",
                   "com.github.uiautomator.test/android.support.test.runner.AndroidJUnitRunner"]

        self.uiautomator_process = self.adb.cmd(*cmd)
        self.adb.forward(self.local_port, self.device_port)

        while not self.alive and timeout > 0:
            time.sleep(0.1)
            timeout -= 0.1
        if not self.alive:
            raise IOError("RPC server not started!")

    def stop(self):
        # print "in FTTAutomatorServer stop"
        if self.uiautomator_process and self.uiautomator_process.poll() is None:
            res = None
            try:
                res = urllib2.urlopen(self.stop_uri)
                self.uiautomator_process.wait()
            except:
                self.uiautomator_process.kill()
            finally:
                if res is not None:
                    res.close()
                self.uiautomator_process = None
        try:
            self.adb.cmd("shell", "am", "force-stop", "com.github.uiautomator").communicate()[0].decode("utf-8").strip().splitlines()
        except Exception, ex:
            pass


class FTTAutomatorDevice(AutomatorDevice):
    def __init__(self, serial=None, local_port=None, adb_server_host=None, adb_server_port=None):
        self.server = FTTAutomatorServer(
            serial=serial,
            local_port=local_port,
            adb_server_host=adb_server_host,
            adb_server_port=adb_server_port
        )
        self.adb = self.server.adb
        self.fttSelector = FTTUISelector(self)
        self.fttJobs = []

    @property
    def source(self):
        return self.fttSelector

    @source.setter
    def source(self, _path):
        self.fttSelector.load(_path)

    def wait_for_times(self, count, interval, error):
        '''
        每隔规定时间等待目前方法执行一次
        :param count: 重试的次数
        :param interval: 每一次重试的时间间隔
        :param error: 超时之后的错误提示
        :return: 一个目标函数的装饰器
        '''
        def decorator(func):
            @wraps(func)
            def wrap_function(*args, **kwargs):
                retry = count
                try:
                    start_time = time.time()
                    if retry == -1:
                        while True:
                            result = func(*args, **kwargs)
                            if result:
                                return result

                    while retry > 0:
                        # print "try to invoke {}".format(func)
                        result = func(*args, **kwargs)
                        if result:
                            return result
                        else:
                            retry -= 1
                        sleep(interval)
                    else:
                        raise EnvironmentError(error)
                finally:
                    self.total_wait_time = time.time() - start_time
            return wrap_function
        return decorator

    def click_selector(self, name, count=20, interval=0.5):
        '''
        点击一个navtive控件
        :param name: ftt-ui-selector定位结构的名字
        :param count: 循环次数
        :param interval: 一次的时间间隔
        :return:
        '''
        return self.fttSelector(name).click() \
            if self.wait_exists_and_enabled(name=name, count=count, interval=interval) else None

    def wait_exists_and_enabled(self, name, count=20, interval=0.5):
        '''
        判断native控件是否存在并且有效
        :param name: ftt-ui-selector定位结构的名字
        :param count: 循环次数
        :param interval: 一次的时间间隔
        :return:
        '''
        ui_selector = self.fttSelector(name)

        @self.wait_for_times(count=count, interval=interval,
                             error="在{0}s内，【{1}】【{2}】没有找到并生效".format(count*interval, self.fttSelector.path, name))
        def is_exists():
            return ui_selector.exists and ui_selector.info['enabled'] is True
        return is_exists()

    def text(self, name):
        '''
        获取ftt-ui-selector的文本内容
        :param name: ftt-ui-selector定位结构的关键字
        :return:
        '''
        return self.fttSelector(name).info['text'].encode('utf-8')

    def wait_exists(self, name, timeout=5000):
        '''
        在一定时间内等待控件出现
        :param name: ftt-ui-selector定位结构的关键字
        :param timeout: 超时时间
        :return:
        '''
        self.fttSelector(name).wait.exists(timeout=timeout)

    def wait_gone(self, name, timeout=5000):
        '''
        在一定时间内等待控件消失
        :param name: ftt-ui-selector定位结构的关键字
        :param timeout: 超时时间
        :return:
        '''
        self.fttSelector(name).wait.gone(timeout=timeout)

    def get_centre(self, name):
        '''
        获取ftt ui selector获取中心点的坐标
        :param name: ftt ui selector
        :return:
        '''
        # Bounds (left,top) (right,bottom)
        bounds = self.fttSelector(name).info['visibleBounds']
        return point((bounds['right'] - bounds['left'])/2 + bounds['left'],
                     (bounds['bottom'] - bounds['top'])/2 + bounds['top'])

    def get_rect(self, name):
        '''
        获取ftt ui selector的矩阵大小
        :param name: ftt ui selector
        :return: {"top": top, "left": left, "bottom": bottom, "right": right}
        '''
        bounds = self.fttSelector(name).info['visibleBounds']
        return rect(**bounds)

    def screen_size(self):
        '''
        返回屏幕尺寸
        :return:
        '''
        return {"width": self.info['displayWidth'],
                "height": self.info['displayHeight']}

    def swipe_to(self, _from, _to, steps=50):
        '''
        从ftt ui selector的_from目标滑动到_to目标,以stps为步长
        :param _from: ftt ui selector
        :param _to: ftt ui selector
        :param steps: 步长
        :return:
        '''
        my_to = self.get_centre(_to)
        my_from = self.get_centre(_from)
        self.swipe(my_from['x'], my_from['y'], my_to['x'], my_to['y'], steps=steps)

    @property
    def swipe_until(self):
        '''
        :Usage:
            >>> # 从experience_device_first选择一个方向滑动到my_unknow_device存在为止
            >>> swipe_until.up('_from', '_to')
            >>> swipe_until('up', '_from', '_to')
            >>> swipe_until.down('_from', '_to')
            >>> swipe_until('down', '_from', '_to')
            >>> swipe_until.left('_from', '_to')
            >>> swipe_until('left', '_from', '_to')
            >>> swipe_until.right('_from', '_to')
            >>> swipe_until('right', '_from', '_to')
        :return:
        '''
        @param_to_property(orientation=['right', 'left', 'up', 'down'])
        def _swipe_until(orientation, _from, _to, steps=100, count=10, interval=0.1):
            '''
            从_from开始滑动直到 _to存在为止
            :param orientation: 滑动方向
            :param _from: ftt ui selector
            :param _to:  ftt ui selector
            :param steps： 滑动步长
            :param count: 滑动次数
            :param interval: 滑动间隔
            '''

            obj = self

            class SwipeHandler(object):
                def __init__(self, name):
                    self.start = obj.get_centre(name)

                @obj.wait_for_times(count=count, interval=interval,
                                    error="朝方向-{0}滑动{1}次后，没有发现{2}".format(orientation,count,_to))
                def until(self):
                    if orientation == 'up':
                        end = point(self.start['x'], self.start['y'] - steps)
                    elif orientation == 'down':
                        end = point(self.start['x'], self.start['y'] + steps)
                    elif orientation == 'left':
                        end = point(self.start['x'] - steps, self.start['y'])
                    elif orientation == 'right':
                        end = point(self.start['x'] + steps, self.start['y'])
                    else:
                        raise EnvironmentError("不支持的滚动方向-{}".format(orientation))
                    obj.swipe(self.start['x'], self.start['y'], end['x'], end['y'], steps=10)
                    return obj.fttSelector(_to).exists
            SwipeHandler(_from).until()
        return _swipe_until

    def watcher(self, name):
        obj = self

        class Watcher(object):
            def __init__(self):
                self.ftt_selectors = []

            @property
            def matched(self):
                @param_to_property(method=['click', 'press'])
                def _matched(method, args=(), kwargs={}):
                    for selector in self.ftt_selectors:
                        if not obj(**selector).exists:
                            return False
                    if method == 'click':
                        if obj(**kwargs).exists:
                            obj(**kwargs).click()
                    elif method == 'press':
                        for arg in args:
                            obj.press(arg)
                return _matched

            def when(self, **kwargs):
                self.ftt_selectors.append(kwargs)
                return self

            def click(self, **kwargs):
                obj.fttJobs.append(FTTJob(name=name, target=lambda: self.matched.click(kwargs=kwargs), interval=1))

            @property
            def press(self):
                @param_to_property(
                    "home", "back", "left", "right", "up", "down", "center",
                    "search", "enter", "delete", "del", "recent", "volume_up",
                    "menu", "volume_down", "volume_mute", "camera", "power")
                def _press(*args):
                    obj.fttJobs.append(FTTJob(name=name, target=lambda: self.matched.press(args=args), interval=1))
                return _press
        return Watcher()

    @property
    def watchers(self):
        obj = self

        class Watchers(list):
            def __init__(self):
                pass

            def find(self, name):
                for job in obj.fttJobs:
                    if job.name == name:
                        return job
                raise EnvironmentError("没有找到task-{}".format(name))

            def pause(self, name):
                self.find(name).pause()

            def resume(self, name):
                self.find(name).resume()

            def run(self, name):
                return self.find(name).start()

            def remove(self, name):
                job = self.find(name)
                job.stop()
                obj.fttJobs.remove(job)

            @property
            def all(self):
                return obj.fttJobs
        return Watchers()


def get_device(serial=None, local_port=None):
    '''
    单例模式，获取创建设备连接
    :param serial: 设备serial
    :param local_port: 本地连接uiautomator的端口
    :return:
    '''
    if get_device.instance:
        return get_device.instance
    else:
        get_device.instance = FTTAutomatorDevice(serial=serial, local_port=local_port)
        return get_device.instance

get_device.instance = None

if __name__ == "__main__":
    FTTDevice = get_device()
    print FTTDevice.info
    FTTDevice.source = u"D:\workspace\IDDAutomation\workspace\layout\\ui\搜索.yaml"
    FTTDevice.source('input_edit').set_text("时达到")
