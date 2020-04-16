# Tiny OpenVINO Inference Engine wrapper class library
# 
# This library conceals the common initialization and process when you use OpenVINO Inference Engine.

import os

import cv2
import numpy as np
from openvino.inference_engine import IENetwork, IECore

class ieWrapper:

    def __init__(self, modelFile=None, device='CPU', numRequest=4):
        self.ie          = IECore()
        self.inferSlot   = 0
        self.callbackFunc= None
        self.inferenceID = 0
        if modelFile == None:
            self.execNet     = None   # exec_net
            self.numRequests = 0
        else:
            fname, ext = os.path.splitext(modelFile)
            self.readModel(fname+'.xml', fname+'.bin', device, numRequest)

    def readModel(self, xmlFile, binFile, device='CPU', numRequest=4):
        net = self.ie.read_network(xmlFile, binFile)
        self.inputs  = {}
        self.outputs = {}
        for inblob in net.inputs:
            self.inputs[inblob] = { 'data' : 0, 'shape' : net.inputs[inblob].shape, 'type' : 'image' }
        for outblob in net.outputs:
            self.outputs[outblob] = { 'shape' : net.outputs[outblob].shape }
        self.execNet = self.ie.load_network(network=net, device_name=device, num_requests=numRequest)
        self.numRequests = numRequest

    # Return information of the inputs of a model
    # The list consists of dictionaries and each dictionary correspond to each input blob
    # The blob marked with 'image' type will go through image preprocessing (resize & transform)
    # e.g. { blobName : { 'data':blobData, 'shape':blobShape, 'type':blobType('imgae' or others)}, ... }
    def getInputs(self):
        return self.inputs

    # Return information of the outputs of a model
    # The list consists of dictionaries and each dictionary correspond to each output blob
    # e.g. { blobName : { 'shape':blobShape }, ... }
    def getOutputs(self):
        return self.outputs

    def callback(self, status, data):
        id, req = data
        outputs = req.outputs
        if self.callbackFunc!=None:
            if(len(outputs)==1):
                firstBlobName = next(iter(self.outputs))
                self.callbackFunc(id, outputs[firstBlobName])   # if the model has only 1 output, return the blob contents in an array
            else:
                self.callbackFunc(id, outputs)                  # if the model has multiple outputs, return the result in dictionary
                                                                # e.g. ( {'prob': array[], 'data': array[]})

    def imagePreprocess(self, img, shape):
        img = cv2.resize(img, (shape[3], shape[2]))
        img = img.transpose((2, 0, 1))
        img = img.reshape(shape)
        return img

    # Creates a dictionary to be consumed as an input of inferencing APIs ( infer(), async_inferar() )
    def createInputBlobDict(self, inputData):
        inBlobList = {}
        if type(inputData) is np.ndarray:      # if the input is single image
            firstBlobName = next(iter(self.inputs))
            resizedImg = self.imagePreprocess(inputData, self.inputs[firstBlobName]['shape'])
            inBlobList = { firstBlobName : resizedImg }
        elif type(inputData) is dict:         # if the input is a list (multiple inputs)
            for k, v in inputData.items():
                if v['type']=='image':        # if the data is image, do preprocess
                    resizedImg = self.imagePreprocess(v['data'], v['shape'])
                    inBlobList[k] = resizedImg
                else:                          # otherwise, just set the data to input blob
                    inBlobList[k] = v['data']
        else:
            raise

        return inBlobList
    
    def asyncInfer(self, img):
        status = None
        while status!=0 and status!=-11:
            req = self.execNet.requests[self.inferSlot]
            self.inferSlot = (self.inferSlot+1) % self.numRequests
            status = req.wait(-1)
        infID = self.inferenceID
        
        inBlobDict = self.createInputBlobDict(img)
        req.set_completion_callback(self.callback, (infID, req))        
        req.async_infer(inputs=inBlobDict)
        self.inferenceID+=1
        return infID
    
    def setCallback(self, callback):
        self.callbackFunc = callback
    
    def waitForAllCompletion(self):
        while True:
            numIdle=0
            for i in range(self.numRequests):
                status = self.execNet.requests[i].wait(-1)
                if status == 0 or status==-11:
                    numIdle+=1
            if numIdle == self.numRequests:
                return

    def blockInfer(self, img):
        inBlobDict = self.createInputBlobDict(img)
        res = self.execNet.infer(inBlobDict)
        if(len(res)==1):
            firstBlobName = next(iter(self.outputs))
            return res[firstBlobName]   # if the model has only 1 output, return the blob contents in an array
        else:
            return res                  # if the model has multiple outputs, return the result in dictionary
                                        # e.g. ( {'prob': array[], 'data': array[]})
