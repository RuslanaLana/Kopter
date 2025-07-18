# -- coding: utf-8 --
import sys
import psutil
import cv2
import numpy as np


from MvImport.MvCameraControl_class import *
from queue import Queue
import gc
import threading
import time
#from config import Config
gc.enable()
#GPIO = None
# if aarch == "aarch64":
#     import Jetson.GPIO as GPIO


#from presenceOrientationCheckService import yoloPresence


winfun_ctype = CFUNCTYPE

stMsgTyp = POINTER(c_uint)
pData = POINTER(c_ubyte)
EventInfoCallBack = winfun_ctype(None, stMsgTyp, c_void_p)

class Camera:
    def __init__(self,camStr="EngravingLinesB\x00"):
        self.cam = None
        self.g_bExit = False
        self.g_bConnect = False
        self.frame_queue = Queue()
        self.trigger=False
        self.camStr=camStr
        #self.config_instance = Config()
        #self.yolo_det=yoloPresence(model_pt=self.config_instance.get_yolo_model_name(),classes=self.config_instance.get_yolo_model_classes())
        #self.yolo_det.presenceCheck(cv2.imread('dummy.png'))
        #print(">>>>>>>>>>>>>>>> YOLO INTIALIZED >>>>>>>>>>>>>>>>>>>>")
        # self.frame=None
        # if GPIO is not None:
        #     GPIO.setmode(GPIO.BOARD)  # BOARD pin-numbering scheme
        # self.loop_pin = 11  # BOARD pin 18
        # if GPIO is not None:
        #     GPIO.setup(self.loop_pin, GPIO.IN)  # Button pin set as input

    def initialize(self):
        SDKVersion = MvCamera.MV_CC_GetSDKVersion()
        print("SDKVersion[0x%x]" % SDKVersion)

        deviceList = MV_CC_DEVICE_INFO_LIST()
        tlayerType = MV_GIGE_DEVICE | MV_USB_DEVICE

        self.CALL_BACK_FUN = EventInfoCallBack(self.exception_callback)
        ret = MvCamera.MV_CC_EnumDevices(tlayerType, deviceList)
        if ret != 0:
            print("enum devices fail! ret[0x%x]" % ret)
            sys.exit()

        if deviceList.nDeviceNum == 0:
            print("find no device!")
            sys.exit()

        print("Find %d devices!" % deviceList.nDeviceNum)

        nConnectionNum = 0
        print(deviceList.nDeviceNum,'p'*9)
        for i in range(0, deviceList.nDeviceNum):
            mvcc_dev_info = cast(deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
            if mvcc_dev_info.nTLayerType == MV_GIGE_DEVICE:
                print("\ngige device: [%d]" % i)
                strModeName = ""

                ##### CHANGED ###############
                #for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chUserDefinedName:
                #    strModeName = strModeName + chr(per)
                #print("device model name: %s" % strModeName)

                # Print the MAC address
                #mac_address = ':'.join(
                #    format(x, '02x') for x in mvcc_dev_info.SpecialInfo.stGigEInfo.chMacAddress)
                #print("MAC address: {}".format(mac_address))
                
                #print("MAC address: {}".format(mvcc_dev_info.SpecialInfo.stGigEInfo.chMacAddress))
                
                #cnt=0

                ##########################################################
                for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chUserDefinedName:
                    strModeName = strModeName + chr(per)
                    #print(chr(per),cnt)
                    #cnt+=1
                print("device model name: %s" % strModeName)

                nConnectionNum = i
                if strModeName == self.camStr:
                    #print('oppo')
                    break

                # nip1 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0xff000000) >> 24)
                # nip2 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x00ff0000) >> 16)
                # nip3 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x0000ff00) >> 8)
                # nip4 = (mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x000000ff)
                # print("current ip: %d.%d.%d.%d\n" % (nip1, nip2, nip3, nip4))

        if int(nConnectionNum) >= deviceList.nDeviceNum:
            print("intput error!")
            sys.exit()

        hThreadHandle = None
        try:
            hThreadHandle = threading.Thread(target=self.reconnect)
            hThreadHandle.start()
        except:
            print("error: unable to start thread")

        hThreadHandle.join()
        self.g_bConnect = False
        self.clear()
        pass

    def exception_callback(self, msgType=0, pUser=None):
        self.g_bConnect = False
        pass

    def reconnect(self):
        while True:
            if self.g_bConnect:
                time.sleep(1)
                continue

            self.clear()

            print("connecting..........")

            deviceList = MV_CC_DEVICE_INFO_LIST()

            # ch:枚举设备 | en:Enum device
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, deviceList)
            if ret != 0:
                print("enum devices fail! ret[0x%x]" % ret)
                time.sleep(1)
                continue

            if deviceList.nDeviceNum == 0:
                print("find no device!")
                time.sleep(1)
                continue

            print("Find %d devices!" % deviceList.nDeviceNum)

            nConnectionNum = 0
            #dev=[]
            for i in range(0, deviceList.nDeviceNum):
                mvcc_dev_info = cast(deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
                print(mvcc_dev_info.SpecialInfo,'0'*6)
                if mvcc_dev_info is None:
                    continue
                if mvcc_dev_info.nTLayerType == MV_GIGE_DEVICE:
                    print("\ngige device: [%d]" % i)
                    strModeName = ""
                    for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chUserDefinedName:
                        strModeName = strModeName + chr(per)
                    print("device model name: %s" % strModeName)
                    #dev.append(strModeName)

                    nConnectionNum = i
                    if strModeName==self.camStr:
                        #print('jiji',dev)
                        break

            if int(nConnectionNum) >= deviceList.nDeviceNum:
                print("intput error!")
                sys.exit()

            # ch:创建相机实例 | en:Creat Camera Object
            self.cam = MvCamera()

            # ch:选择设备并创建句柄| en:Select device and create handle
            stDeviceList = cast(deviceList.pDeviceInfo[int(nConnectionNum)], POINTER(MV_CC_DEVICE_INFO)).contents

            ret = self.cam.MV_CC_CreateHandle(stDeviceList)
            if ret != 0:
                print("create handle fail! ret[0x%x]" % ret)
                sys.exit()

            # ch:打开设备 | en:Open device
            ret = self.cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            if ret != 0:
                print("open device fail! ret[0x%x]" % ret)
                sys.exit()

            self.g_bConnect = True

            # ch:探测网络最佳包大小(只对GigE相机有效) | en:Detection network optimal package size(It only works for the GigE camera)
            if stDeviceList.nTLayerType == MV_GIGE_DEVICE:
                nPacketSize = self.cam.MV_CC_GetOptimalPacketSize()
                if int(nPacketSize) > 0:
                    ret = self.cam.MV_CC_SetIntValue("GevSCPSPacketSize", nPacketSize)
                    if ret != 0:
                        print("Warning: Set Packet Size fail! ret[0x%x]" % ret)
                else:
                    print("Warning: Get Packet Size fail! ret[0x%x]" % nPacketSize)

            # ch:设置触发模式为off | en:Set trigger mode as off
            ret = self.cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
            if ret != 0:
                print("set trigger mode fail! ret[0x%x]" % ret)
                sys.exit()

            # ch:获取数据包大小 | en:Get payload size
            stParam = MVCC_INTVALUE()
            memset(byref(stParam), 0, sizeof(MVCC_INTVALUE))

            ret = self.cam.MV_CC_GetIntValue("PayloadSize", stParam)
            if ret != 0:
                print("get payload size fail! ret[0x%x]" % ret)
                sys.exit()
            nPayloadSize = stParam.nCurValue

            ret = self.cam.MV_CC_RegisterExceptionCallBack(self.CALL_BACK_FUN, None)
            if ret != 0:
                print("exception callback fail! ret[0x%x]" % ret)
                sys.exit()

            # ch:开始取流 | en:Start grab image
            ret = self.cam.MV_CC_StartGrabbing()
            if ret != 0:
                print("start grabbing fail! ret[0x%x]" % ret)
                sys.exit()

            try:
                hThreadHandle = threading.Thread(target=self.image_buf_thread, args=(nPayloadSize,))
                hThreadHandle.start()
            except:
                print("error: unable to start thread")
        pass

    def convert_pixel_format(self, data_buf, stFrameInfo):
        nparr = None
        pDataForRGB = stFrameInfo.nWidth * stFrameInfo.nHeight * 3
        if pDataForRGB is not None:
            # 填充存图参数
            # fill in the parameters  of save image

            stConvertParam = MV_CC_PIXEL_CONVERT_PARAM()
            memset(byref(stConvertParam), 0, sizeof(stConvertParam))
            # // 从上到下依次是：输出图片格式，输入数据的像素格式，提供的输出缓冲区大小，图像宽，
            # // 图像高，输入数据缓存，输出图片缓存，JPG编码质量
            # Top to bottom are：
            stConvertParam.nWidth = stFrameInfo.nWidth
            stConvertParam.nHeight = stFrameInfo.nHeight
            print(type(data_buf))
            stConvertParam.pSrcData = data_buf
            stConvertParam.nSrcDataLen = stFrameInfo.nFrameLen
            stConvertParam.enSrcPixelType = stFrameInfo.enPixelType
            stConvertParam.enDstPixelType = PixelType_Gvsp_RGB8_Packed
            stConvertParam.pDstBuffer = (c_ubyte * pDataForRGB)()
            stConvertParam.nDstBufferSize = pDataForRGB
            ret = self.cam.MV_CC_ConvertPixelType(stConvertParam)
            print(">>>>> RET >>>>>>",ret)
            if ret != 0:
                print("convert pixel fail! ret[0x%x]" % ret)
                del data_buf
                sys.exit()

            # print("Convent OK")
            try:
                img_buff = (c_ubyte * stConvertParam.nDstLen)()
                memmove(byref(img_buff), stConvertParam.pDstBuffer, stConvertParam.nDstLen)

                nparr = np.frombuffer(img_buff, np.uint8)
                # print("shape of buffer ", nparr.shape)
                # print(nparr)
                nparr = nparr.reshape(stFrameInfo.nHeight, stFrameInfo.nWidth, 3)
                nparr = cv2.cvtColor(nparr, cv2.COLOR_RGB2BGR)
                # cv2.imshow('Yolo_nparr',nparr)
                # cv2.waitKey(0)
                # cv2.destroyAllWindows()
                # nparr = cv2.rotate(nparr, cv2.ROTATE_180)
                # nparr = cv2.resize(nparr, config_instance.get_Img_resize())
                # yolo = 0
                # result = yolo_det.presenceCheck(nparr)
                # print("YOLO INF IN CAMERA MODULE",time.time()-yolo)
                # self.frame_queue.put([nparr, result])
            except:
                raise Exception("save file executed failed")

        return nparr

    def image_buf_thread(self, nPayloadSize=0):
        stFrameInfo = MV_FRAME_OUT_INFO_EX()
        memset(byref(stFrameInfo), 0, sizeof(stFrameInfo))
        data_buf = (c_ubyte * nPayloadSize)()
        previous = None
        nparr=[]
        while True:
            object_present = False
            if not self.g_bConnect:
                del data_buf
                break

            # Need tigger for capture frame
            # For now we are using key enter key
            # time.sleep(0.2)
            # if GPIO is not None:
            #     current = GPIO.input(self.loop_pin)
            # if current != previous:
            #     if current == 0:
            #         print("Object present--------------------")
            #         object_present = True
            #         pass
            #     elif current == 1:
            #         pass
            #     else:
            #         pass
            # else:
            #     pass
            # previous = current

            '''if not object_present:
                time.sleep(0.1)
                continue'''

            # input("Press enter to capture frame-------------")

            ret = self.cam.MV_CC_GetOneFrameTimeout(byref(data_buf), nPayloadSize, stFrameInfo, 1000)
            if self.trigger:

                pDataForRGB = stFrameInfo.nWidth * stFrameInfo.nHeight * 3
                if pDataForRGB is not None:
                    # 填充存图参数
                    # fill in the parameters  of save image

                    stConvertParam = MV_CC_PIXEL_CONVERT_PARAM()
                    memset(byref(stConvertParam), 0, sizeof(stConvertParam))
                    # // 从上到下依次是：输出图片格式，输入数据的像素格式，提供的输出缓冲区大小，图像宽，
                    # // 图像高，输入数据缓存，输出图片缓存，JPG编码质量
                    # Top to bottom are：
                    stConvertParam.nWidth = stFrameInfo.nWidth
                    stConvertParam.nHeight = stFrameInfo.nHeight
                    # print(type(data_buf))
                    stConvertParam.pSrcData = data_buf
                    stConvertParam.nSrcDataLen = stFrameInfo.nFrameLen
                    stConvertParam.enSrcPixelType = stFrameInfo.enPixelType
                    stConvertParam.enDstPixelType = PixelType_Gvsp_RGB8_Packed
                    stConvertParam.pDstBuffer = (c_ubyte * pDataForRGB)()
                    stConvertParam.nDstBufferSize = pDataForRGB
                    nRet = self.cam.MV_CC_ConvertPixelType(stConvertParam)
                    # print(ret)
                    if ret != 0:
                        print("convert pixel fail! ret[0x%x]" % ret)
                        del data_buf
                        sys.exit()

                    # print("Convent OK")
                    try:
                        img_buff = (c_ubyte * stConvertParam.nDstLen)()
                        memmove(byref(img_buff), stConvertParam.pDstBuffer, stConvertParam.nDstLen)

                        nparr = np.frombuffer(img_buff, np.uint8)
                        # print("shape of buffer ", nparr.shape)
                        # print(nparr)
                        
                        nparr = nparr.reshape(stFrameInfo.nHeight, stFrameInfo.nWidth, 3)
                        nparr = cv2.cvtColor(nparr, cv2.COLOR_RGB2BGR)
                        #print("NPARR",nparr)
                        if nparr is not None:
                            #Sprint("-----------------------------------------",nparr.shape)
                        # self.frame=nparr
                            #frame = cv2.resize(nparr, self.config_instance.get_Img_resize())
                            frame = cv2.rotate(nparr, cv2.ROTATE_180)
                            #result = self.yolo_det.presenceCheck(frame)
                            #print("Result in Yolo",result)
                            #if result !=[]:
                            self.frame_queue.put(frame)
                        else:
                            #print("Result in Yolo",result)
                            print("Image is None")
                            #self.frame_queue.put([nparr,result])
                        

                    except:
                        raise Exception("save file executed failed")
    # def get_img(self):
    #     return self.frame

    def clear(self):
        # ch:停止取流 | en:Stop grab image
        if self.cam is not None:
            ret = self.cam.MV_CC_StopGrabbing()
            if ret != 0:
                print("stop grabbing fail! ret[0x%x]" % ret)
                # sys.exit()

            # ch:关闭设备 | Close device
            ret = self.cam.MV_CC_CloseDevice()
            if ret != 0:
                print("close deivce fail! ret[0x%x]" % ret)
                # sys.exit()

            # ch:销毁句柄 | Destroy handle
            ret = self.cam.MV_CC_DestroyHandle()
            if ret != 0:
                print("destroy handle fail! ret[0x%x]" % ret)
                # sys.exit()
            pass


#save_dir = "./bottleData/13Sept2022/"


def create_directory(save_dir):
    try:
        os.makedirs(save_dir)
    except Exception as e:
        print(e)
        pass

if __name__ == "__main__":
    print(f"CPU utilization: {psutil.cpu_percent()}%")
    print(f"Memory utilization: {psutil.virtual_memory().percent}%")
    camera = Camera()
    c_thread = threading.Thread(target=camera.initialize)
    c_thread.start()
    # create_directory()
    i = 0
    camera.trigger=True
    frame=None
    while True:
        try:
            frame = camera.frame_queue.get()
            print(frame.shape)
        except:
            print('no frame')
            pass
        
      #  print("Queue Length:", camera.frame_queue.qsize())
        #if frame is not None:
        #    print(frame.shape)
        #    cv2.imshow('kaoks',frame)
        #    cv2.waitKey(1)
        print(f"CPU utilization: {psutil.cpu_percent()}%")
        print(f"Memory utilization: {psutil.virtual_memory().percent}%")

        # cv2.imwrite(save_dir + "/Frame_" + str(i) + "_" + str(int(time.time())) + ".jpg", frame)
        #i += 1
    #pass



