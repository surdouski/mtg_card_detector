import cv2
import numpy as np
import os
import sys
from operator import itemgetter


# Disclaimer: majority of the basic framework in this file is modified from the following tutorial:
# https://www.learnopencv.com/deep-learning-based-object-detection-using-yolov3-with-opencv-python-c/


# Get the names of the output layers
def get_outputs_names(net):
    # Get the names of all the layers in the network
    layers_names = net.getLayerNames()
    # Get the names of the output layers, i.e. the layers with unconnected outputs
    return [layers_names[i[0] - 1] for i in net.getUnconnectedOutLayers()]


# Remove the bounding boxes with low confidence using non-maxima suppression
def post_process(frame, outs, thresh_conf, thresh_nms):
    frame_height = frame.shape[0]
    frame_width = frame.shape[1]

    # Scan through all the bounding boxes output from the network and keep only the
    # ones with high confidence scores. Assign the box's class label as the class with the highest score.
    class_ids = []
    confidences = []
    boxes = []
    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > thresh_conf:
                center_x = int(detection[0] * frame_width)
                center_y = int(detection[1] * frame_height)
                width = int(detection[2] * frame_width)
                height = int(detection[3] * frame_height)
                left = int(center_x - width / 2)
                top = int(center_y - height / 2)
                class_ids.append(class_id)
                confidences.append(float(confidence))
                boxes.append([left, top, width, height])

    # Perform non maximum suppression to eliminate redundant overlapping boxes with lower confidences.
    indices = [ind[0] for ind in cv2.dnn.NMSBoxes(boxes, confidences, thresh_conf, thresh_nms)]
    
    ret = [[class_ids[i], confidences[i], boxes[i]] for i in indices]
    return ret


# Draw the predicted bounding box
def draw_pred(frame, class_id, classes, conf, left, top, right, bottom):
    # Draw a bounding box.
    cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255))

    label = '%.2f' % conf

    # Get the label for the class name and its confidence
    if classes:
        assert (class_id < len(classes))
        label = '%s:%s' % (classes[class_id], label)

    # Display the label at the top of the bounding box
    label_size, base_line = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    top = max(top, label_size[1])
    cv2.putText(frame, label, (left, top), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255))


def remove_glare(img):
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    _, s, v = cv2.split(img_hsv)
    non_sat = (s < 32) * 255  # Find all pixels that are not very saturated

    # Slightly decrease the area of the non-satuared pixels by a erosion operation.
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    non_sat = cv2.erode(non_sat.astype(np.uint8), disk)

    # Set all brightness values, where the pixels are still saturated to 0.
    v[non_sat == 0] = 0
    # filter out very bright pixels.
    glare = (v > 240) * 255

    # Slightly increase the area for each pixel
    glare = cv2.dilate(glare.astype(np.uint8), disk)
    #glare = cv2.dilate(glare.astype(np.uint8), disk);

    #corrected = cv2.inpaint(img, glare, 7, cv2.INPAINT_TELEA)
    glare_reduced = np.ones((img.shape[0], img.shape[1], 3), dtype=np.uint8) * 200
    glare = cv2.cvtColor(glare, cv2.COLOR_GRAY2BGR)
    corrected = np.where(glare, glare_reduced, img)
    return corrected


def detect_frame(net, classes, img, thresh_conf=0.5, thresh_nms=0.4, in_dim=(416, 416), display=True, out_path=None):
    img_copy = img.copy()
    # Create a 4D blob from a frame.
    blob = cv2.dnn.blobFromImage(img, 1 / 255, in_dim, [0, 0, 0], 1, crop=False)

    # Sets the input to the network
    net.setInput(blob)

    # Runs the forward pass to get output of the output layers
    outs = net.forward(get_outputs_names(net))

    # Remove the bounding boxes with low confidence
    obj_list = post_process(img, outs, thresh_conf, thresh_nms)
    for obj in obj_list:
        class_id, confidence, box = obj
        left, top, width, height = box
        draw_pred(img, class_id, classes, confidence, left, top, left + width, top + height)

    # Put efficiency information. The function getPerfProfile returns the
    # overall time for inference(t) and the timings for each of the layers(in layersTimes)
    t, _ = net.getPerfProfile()
    label = 'Inference time: %.2f ms' % (t * 1000.0 / cv2.getTickFrequency())
    cv2.putText(img, label, (0, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255))

    if out_path is not None:
        cv2.imwrite(out_path, img.astype(np.uint8))
    if display:
        no_glare = remove_glare(img_copy)
        img_concat = np.concatenate((img, no_glare), axis=1)
        cv2.imshow('result', img_concat)

        '''
        for i in range(len(obj_list)):
            class_id, confidence, box = obj_list[i]
            left, top, width, height = box
            img_snip = img[max(0, top):min(img.shape[0], top + height), max(0, left):min(img.shape[1], left + width)]
            #cv2.imshow('feature#%d' % i, img_snip)
            img_hsv = cv2.cvtColor(img_snip, cv2.COLOR_BGR2HSV)
            h, s, v = cv2.split(img_hsv)
            #h = cv2.cvtColor(h, cv2.COLOR_GRAY2BGR)
            s = cv2.cvtColor(s, cv2.COLOR_GRAY2BGR)
            v = cv2.cvtColor(v, cv2.COLOR_GRAY2BGR)
            img_concat = np.concatenate((img_snip, s, v), axis=1)
            cv2.imshow('feature#%d - hsv' % i, img_concat)
        '''
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return obj_list


def detect_video(net, classes, capture, thresh_conf=0.5, thresh_nms=0.4, in_dim=(416, 416), display=True, out_path=None):
    if out_path is not None:
        vid_writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'), 30,
                                     (round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                                      round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))))
    max_num_obj = 0
    while True:
        ret, frame = capture.read()
        if not ret:
            # End of video
            print("End of video. Press any key to exit")
            cv2.waitKey(0)
            break
        img = frame.copy()
        obj_list = detect_frame(net, classes, frame, thresh_conf=thresh_conf, thresh_nms=thresh_nms, in_dim=in_dim,
                                display=False, out_path=None)
        max_num_obj = max(max_num_obj, len(obj_list))
        if display:
            no_glare = remove_glare(img)
            img_concat = np.concatenate((frame, no_glare), axis=1)
            cv2.imshow('result', img_concat)
            '''
            for i in range(len(obj_list)):
                class_id, confidence, box = obj_list[i]
                left, top, width, height = box
                img_snip = img[max(0, top):min(img.shape[0], top + height),
                           max(0, left):min(img.shape[1], left + width)]
                # cv2.imshow('feature#%d' % i, img_snip)
                img_hsv = cv2.cvtColor(img_snip, cv2.COLOR_BGR2HSV)
                h, s, v = cv2.split(img_hsv)
                # h = cv2.cvtColor(h, cv2.COLOR_GRAY2BGR)
                s = cv2.cvtColor(s, cv2.COLOR_GRAY2BGR)
                v = cv2.cvtColor(v, cv2.COLOR_GRAY2BGR)
                img_concat = np.concatenate((img_snip, s, v), axis=1)
                cv2.imshow('feature#%d - hsv' % i, img_concat)
            for i in range(len(obj_list), max_num_obj):
                cv2.imshow('feature#%d - hsv' % i, np.zeros((1, 1), dtype=np.uint8))
            '''
            #if len(obj_list) > 0:
                #cv2.waitKey(0)
        if out_path is not None:
            vid_writer.write(frame.astype(np.uint8))
        cv2.waitKey(1)

    if out_path is not None:
        vid_writer.release()
    cv2.destroyAllWindows()


def main():
    # Specify paths for all necessary files
    test_path = os.path.abspath('../data/test18.jpg')
    weight_path = 'weights/second_general/tiny_yolo_final.weights'
    cfg_path = 'cfg/tiny_yolo.cfg'
    class_path = "data/obj.names"
    out_dir = 'out'
    if not os.path.isfile(test_path):
        print('The test file %s doesn\'t exist!' % os.path.abspath(test_path))
        return
    if not os.path.isfile(weight_path):
        print('The weight file %s doesn\'t exist!' % os.path.abspath(test_path))
        return
    if not os.path.isfile(cfg_path):
        print('The config file %s doesn\'t exist!' % os.path.abspath(test_path))
        return
    if not os.path.isfile(class_path):
        print('The class file %s doesn\'t exist!' % os.path.abspath(test_path))
        return

    # Setup
    # Read class names from text file
    with open(class_path, 'r') as f:
        classes = [line.strip() for line in f.readlines()]
    # Load up the neural net using the config and weights
    net = cv2.dnn.readNetFromDarknet(cfg_path, weight_path)
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    # Save the detection result if out_dir is provided
    if out_dir is None or out_dir == '':
        out_path = None
    else:
        out_path = out_dir + '/' + os.path.split(test_path)[1]
    # Check if test file is image or video
    test_ext = test_path[test_path.find('.') + 1:]

    if test_ext in ['jpg', 'jpeg', 'bmp', 'png', 'tiff']:
        img = cv2.imread(test_path)
        detect_frame(net, classes, img, out_path=out_path)
    else:
        capture = cv2.VideoCapture(test_path)
        detect_video(net, classes, capture, out_path=out_path)
        capture.release()
    pass


if __name__ == '__main__':
    main()
