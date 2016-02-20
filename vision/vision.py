import time

import cv2
from pylab import *
from scipy.ndimage import measurements
from scipy.spatial import distance

from strategy.world import NO_VALUE

VISION_ROOT = 'vision/'
KNOWN_ANGLE = 225
COLOR_RANGES = {
    'red': [((0, 170, 130), (8, 255, 255)), ((175, 170, 130), (180, 255, 255))],
    'blue': [((83, 110, 150), (102, 230, 230))],
    'yellow': [((30, 150, 150), (37, 255, 255))],
    'pink': [((149, 130, 60), (175, 255, 255))],
    'green': [((50, 130, 200), (55, 255, 255))],
}

MAX_COLOR_COUNTS = {
    'red': 1,
    'blue': 10,
    'yellow': 2,
    'pink': 8,
    'green': 8,
}

COLORS = {
    'red': (0, 0, 255),
    'blue': (255, 0, 0),
    'yellow': (0, 255, 255),
    'pink': (153, 51, 255),
    'green': (0, 255, 0),
}

MIN_COLOR_AREA = {
    'red': 1000.0,
    'blue': 0.0,
    'yellow': 1000.0,
    'pink': 1000.0,
    'green': 1000.0,
}

VENUS = 0
TEAMMATE = 1
ENEMY_1 = 2
ENEMY_2 = 3


class Vision:
    def __init__(self, world, debug=False):
        self.debug = debug
        self.world = world
        self.pressed_key = None
        self.trajectory_list = [(0, 0)]*6
        if self.world.room_num == 1:
            self.mtx = np.loadtxt(VISION_ROOT + "mtx1.txt")
            self.dist = np.loadtxt(VISION_ROOT + "dist1.txt")
            self.pts1 = np.float32([[33, 12], [609, 16], [607, 475], [22, 462]])
            # self.pts1 = np.float32([[10, 2], [634, 37], [596, 478], [6, 456]])
        elif self.world.room_num == 0:
            self.mtx = np.loadtxt(VISION_ROOT + "mtx2.txt")
            self.dist = np.loadtxt(VISION_ROOT + "dist2.txt")
            self.pts1 = np.float32([[33, 12], [609, 16], [607, 475], [22, 462]])
            # self.pts1 = np.float32([[7, 5], [607, 4], [593, 451], [17, 450]])
        else:
            print("invalid room id")

        self.capture = cv2.VideoCapture(0)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 600)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 440)
        self.capture.set(cv2.CAP_PROP_BRIGHTNESS, .5)
        self.capture.set(cv2.CAP_PROP_CONTRAST, .5)
        self.capture.set(cv2.CAP_PROP_SATURATION, .5)
        self.capture.set(cv2.CAP_PROP_HUE, .5)

        while self.pressed_key != 27:
        #for a in xrange(0, 10):
            self.frame()
        cv2.destroyAllWindows()
        return

    def frame(self):
        # print "--------------------"
        # self.start = time.time()

        status, frame = self.capture.read()
        h, w = frame.shape[:2]
        newcameramtx, roi = cv2.getOptimalNewCameraMatrix(self.mtx, self.dist, (w, h), 0, (w, h))

        # These are the actual values needed to undistort:
        dst = cv2.undistort(frame, self.mtx, self.dist, None, newcameramtx)

        # print "undistort", time.time() - self.start
        # self.start = time.time()

        # crop the image
        x, y, w, h = roi
        dst = dst[y:y + h, x:x + w]

        # print "crop", time.time() - self.start
        # self.start = time.time()

        # Apply perspective transformation
        pts2 = np.float32([[0, 0], [639, 0], [639, 479], [0, 479]])
        M = cv2.getPerspectiveTransform(self.pts1, pts2)
        imgOriginal = cv2.warpPerspective(dst, M, (639, 479))

        # print "transform", time.time() - self.start
        # self.start = time.time()

        # Image Masking
        imgHSV = cv2.cvtColor(imgOriginal, cv2.COLOR_BGR2HSV)

        # print "bgr2hsv", time.time() - self.start
        # self.start = time.time()

        circles = {}
        for color_name, color_ranges in COLOR_RANGES.iteritems():
            circles[color_name] = self.TrackCircle(color_name, color_ranges, imgOriginal, imgHSV)

            # print "trackcircle", color_name, time.time() - self.start
            # self.start = time.time()

        # draws circles spotted
        if self.debug:
            print '----------'
        for color_name, positions in circles.iteritems():
            if self.debug:
                print 'Detected ' + color_name + ' : ' + str(len(positions))
            for x, y, area, color in positions:
                cv2.circle(imgOriginal, (int(x), int(y)), 8, COLORS[color_name], 1)

            # save balls trajectory
            if color_name == 'red':
                for x, y, area, color in positions:
                    self.trajectory_list.append((x, y))
                    self.trajectory_list.pop(0)

        # print "drawing", time.time() - self.start
        # self.start = time.time()

        # draw balls trajectory
        delta_x = self.trajectory_list[len(self.trajectory_list) - 1][0] - self.trajectory_list[0][0]
        if abs(delta_x) > 2:
            self.world.ball_moving.value = True
            future_x = self.trajectory_list[len(self.trajectory_list) - 1][0] + 2.0 * delta_x
            m = (self.trajectory_list[len(self.trajectory_list) - 1][1] - self.trajectory_list[0][1]) / float(delta_x)
            future_y = (future_x - self.trajectory_list[0][0]) * m + self.trajectory_list[0][1]
            self.world.future_ball[0] = int(future_x)
            self.world.future_ball[1] = int(future_y)
            cv2.line(imgOriginal, (int(self.trajectory_list[len(self.trajectory_list) - 1][0])
                                   , int(self.trajectory_list[len(self.trajectory_list) - 1][1]))
                     , (int(future_x), int(future_y)), COLORS['red'], 1)
        else:
            self.world.ball_moving.value = False

        # print "trajectory", time.time() - self.start
        # self.start = time.time()

        self.getRobots(circles)
        self.getBall(circles)

        # print "robots", time.time() - self.start
        # self.start = time.time()

        for robot_id, robot in enumerate([self.world.venus, self.world.friend, self.world.enemy1, self.world.enemy2]):
            if robot.position[0] != NO_VALUE:
                cv2.rectangle(imgOriginal, (robot.position[0] - 20, robot.position[1] - 20),
                              (robot.position[0] + 20, robot.position[1] + 20), self.robot_color(robot_id), 2)
                cv2.arrowedLine(imgOriginal, (robot.position[0], robot.position[1]),
                                (int(robot.position[0] + robot.orientation[0] * 50.0),
                                 int(robot.position[1] + robot.orientation[1] * 50.0)),
                                self.robot_color(robot_id), 2)
                cv2.putText(imgOriginal, str(robot_id), (robot.position[0] + 20, robot.position[1] + 40),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            2, self.robot_color(robot_id))

        # print "drawrobots", time.time() - self.start
        # self.start = time.time()

        cv2.namedWindow("Room", cv2.WINDOW_AUTOSIZE)
        cv2.imshow('Room', imgOriginal)
        self.pressed_key = cv2.waitKey(2) & 0xFF

    def robot_color(self, r_id):
        if r_id == 0:
            return COLORS['green']
        elif r_id == 1:
            return COLORS['yellow']
        elif r_id == 2:
            return COLORS['red']
        elif r_id == 3:
            return COLORS['red']

    # returns one ball
    def getBall(self, circles):
        if len(circles['red']) == 0:
            self.world.ball[0] = NO_VALUE
            self.world.ball[1] = NO_VALUE
        else:
            self.world.ball[0] = int(circles['red'][0][0])
            self.world.ball[1] = int(circles['red'][0][1])

    def getRobots(self, circles):
        self.single_angle = - 150
        self.triple_angle = 54
        pointList = circles["green"] + circles["pink"] + circles["blue"] + circles["yellow"]
        pointsSorted = sorted(pointList, key=lambda x: x[2], reverse=True)
        pointsUsed = []
        robots = []
        robots.append({'pink': [], 'blue': [], 'green': [], 'yellow': []})
        robots.append({'pink': [], 'blue': [], 'green': [], 'yellow': []})
        robots.append({'pink': [], 'blue': [], 'green': [], 'yellow': []})
        robots.append({'pink': [], 'blue': [], 'green': [], 'yellow': []})
        robotCounter = 0
        for point in pointsSorted:
            if point[1] > 10 and pointsSorted is not None and point not in pointsUsed:  # dodgy blue stuff in top left
                pointsUsed.append(point)
                localPoints = []
                counter = 0
                if pointsSorted is not None:
                    for localPoint in pointsSorted:
                        if sqrt((point[0] - localPoint[0])**2 + (point[1] - localPoint[1])**2) < 25:
                            counter += 1
                            localPoints.append(localPoint)
                            pointsUsed.append(localPoint)
                    if robotCounter < 4:
                        for robotPoint in localPoints:
                            if robotPoint[3] == 'pink':
                                robots[robotCounter]['pink'].append(robotPoint)
                            if robotPoint[3] == 'blue':
                                robots[robotCounter]['blue'].append(robotPoint)
                            if robotPoint[3] == 'green':
                                robots[robotCounter]['green'].append(robotPoint)
                            if robotPoint[3] == 'yellow':
                                robots[robotCounter]['yellow'].append(robotPoint)
                    robotCounter += 1
        ################################################################
        venus = False
        friend = False
        enemy1 = False
        enemy2 = False
        for robot in robots:
            if len(robot['blue']) == 1 and len(robot['yellow']) == 0 and len(robot['pink']) == 3 or len(
                    robot['blue']) == 1 and len(robot['yellow']) == 0 and len(robot['green']) == 1:
                self.findVenus(robot)
                venus = True
            elif len(robot['blue']) == 1 and len(robot['yellow']) == 0 and len(robot['green']) == 3 or len(
                    robot['blue']) == 1 and len(robot['yellow']) == 0 and len(robot['pink']) == 1:
                self.findFriend(robot)
                friend = True
            elif len(robot['yellow']) == 1 and len(robot['blue']) == 0 and len(robot['pink']) == 3 or len(
                    robot['yellow']) == 1 and len(robot['blue']) == 0 and len(robot['green']) == 1:
                self.findEnemy1(robot)
                enemy1 = True
            elif len(robot['yellow']) == 1 and len(robot['blue']) == 0 and len(robot['green']) == 3 or len(
                    robot['yellow']) == 1 and len(robot['blue']) == 0 and len(robot['pink']) == 1:
                self.findEnemy2(robot)
                enemy2 = True
            elif len(robot['blue']) < 2 and len(robot['yellow']) == 0 and len(robot['pink']) > 1 or len(
                    robot['blue']) < 2 and len(robot['yellow']) == 0 and len(robot['green']) < 2:
                self.findVenus(robot)
                venus = True
            elif len(robot['blue']) < 2 and len(robot['yellow']) == 0 and len(robot['green']) > 1 or len(
                    robot['blue']) < 2 and len(robot['yellow']) == 0 and len(robot['pink']) < 2:
                self.findFriend(robot)
                friend = True
            elif len(robot['yellow']) < 2 and len(robot['blue']) == 0 and len(robot['pink']) > 1 or len(
                    robot['yellow']) < 2 and len(robot['blue']) == 0 and len(robot['green']) < 2:
                self.findEnemy1(robot)
                enemy1 = True
            elif len(robot['yellow']) < 2 and len(robot['blue']) == 0 and len(robot['green']) > 1 or len(
                    robot['yellow']) < 2 and len(robot['blue']) == 0 and len(robot['pink']) < 2:
                self.findEnemy2(robot)
                enemy2 = True
            else:
                print "missing robot"
        if venus is False :
            angle = math.degrees(math.atan2(self.world.venus.orientation[0], self.world.venus.orientation[1]))
            self.save_robot((self.world.venus.position[0], self.world.venus.position[1]), angle, 0)
        if friend is False :
            angle = math.degrees(math.atan2(self.world.friend.orientation[0], self.world.friend.orientation[1]))
            self.save_robot((self.world.friend.position[0], self.world.friend.position[1]), angle, 1)
        if enemy1 is False :
            angle = math.degrees(math.atan2(self.world.enemy1.orientation[0], self.world.enemy1.orientation[1]))
            self.save_robot((self.world.enemy1.position[0], self.world.enemy1.position[1]), angle, 2)
        if enemy2 is False :
            angle = math.degrees(math.atan2(self.world.enemy2.orientation[0], self.world.enemy2.orientation[1]))
            self.save_robot((self.world.enemy2.position[0], self.world.enemy2.position[1]), angle, 3)
                # venus
                ###################################################################################################################

    def findVenus(self, robot):
        if len(robot['green']) == 1 and len(robot['blue']) == 1:
            angle = math.degrees(math.atan2(robot['green'][0][0] - robot['blue'][0][0],
                                            robot['green'][0][1] - robot['blue'][0][1])) + self.single_angle
            self.save_robot((robot['blue'][0][0], robot['blue'][0][1]), angle, 0)
        elif len(robot['pink']) == 3:
            dist = []
            point_1 = []
            point_2 = []
            dist.append(sqrt(
                (robot['pink'][0][0] - robot['pink'][1][0]) ** 2 + (robot['pink'][0][1] - robot['pink'][1][1]) ** 2))

            dist.append(sqrt(
                (robot['pink'][1][0] - robot['pink'][2][0]) ** 2 + (robot['pink'][1][1] - robot['pink'][2][1]) ** 2))

            dist.append(sqrt(
                (robot['pink'][2][0] - robot['pink'][0][0]) ** 2 + (robot['pink'][2][1] - robot['pink'][0][1]) ** 2))

            point_1.append((robot['pink'][(dist.index(max(dist))) % 3][0] +
                            robot['pink'][(dist.index(max(dist)) + 1) % 3][0]) / 2.0)
            point_1.append((robot['pink'][(dist.index(max(dist))) % 3][1] +
                            robot['pink'][(dist.index(max(dist)) + 1) % 3][1]) / 2.0)
            point_2.append(robot['pink'][(dist.index(max(dist)) + 2) % 3][0])
            point_2.append(robot['pink'][(dist.index(max(dist)) + 2) % 3][1])
            angle = math.degrees(math.atan2(point_2[0] - point_1[0], point_2[1] - point_1[1])) + self.triple_angle
            center_x = (robot['pink'][(dist.index(max(dist))) % 3][0] + robot['pink'][(dist.index(max(dist)) + 1) % 3][
                0]) / 2.0  # add something here
            center_y = (robot['pink'][(dist.index(max(dist))) % 3][1] + robot['pink'][(dist.index(max(dist)) + 1) % 3][
                1]) / 2.0  # add something here
            self.save_robot((center_x, center_y), angle, 0)
        elif len(robot['blue']) == 1:
            angle = math.degrees(math.atan2(self.world.venus.orientation[0], self.world.venus.orientation[1]))
            self.save_robot((robot['blue'][0][0], robot['blue'][0][1]), angle, 0)
        else:
            angle = math.degrees(math.atan2(self.world.venus.orientation[0], self.world.venus.orientation[1]))
            self.save_robot((self.world.venus.position[0], self.world.venus.position[1]), angle, 0)

            # Team mate
            ####################################################################################################################

    def findFriend(self, robot):
        if len(robot['green']) == 1 and len(robot['blue']) == 1:
            angle = math.degrees(math.atan2(robot['green'][0][0] - robot['blue'][0][0],
                                            robot['green'][0][1] - robot['blue'][0][1])) + self.single_angle
            self.save_robot((robot['blue'][0][0], robot['blue'][0][1]), angle, 1)
        elif len(robot['green']) == 3:
            dist = []
            point_1 = []
            point_2 = []
            dist.append(sqrt((robot['green'][0][0] - robot['green'][1][0]) ** 2 + (
            robot['green'][0][1] - robot['green'][1][1]) ** 2))

            dist.append(sqrt((robot['green'][1][0] - robot['green'][2][0]) ** 2 + (
            robot['green'][1][1] - robot['green'][2][1]) ** 2))

            dist.append(sqrt((robot['green'][2][0] - robot['green'][0][0]) ** 2 + (
            robot['green'][2][1] - robot['green'][0][1]) ** 2))

            point_1.append((robot['green'][(dist.index(max(dist))) % 3][0] +
                            robot['green'][(dist.index(max(dist)) + 1) % 3][0]) / 2.0)
            point_1.append((robot['green'][(dist.index(max(dist))) % 3][1] +
                            robot['green'][(dist.index(max(dist)) + 1) % 3][1]) / 2.0)
            point_2.append(robot['green'][(dist.index(max(dist)) + 2) % 3][0])
            point_2.append(robot['green'][(dist.index(max(dist)) + 2) % 3][1])
            angle = math.degrees(math.atan2(point_2[0] - point_1[0], point_2[1] - point_1[1])) + self.triple_angle
            center_x = (
                       robot['green'][(dist.index(max(dist))) % 3][0] + robot['green'][(dist.index(max(dist)) + 1) % 3][
                           0]) / 2.0  # add something here
            center_y = (
                       robot['green'][(dist.index(max(dist))) % 3][1] + robot['green'][(dist.index(max(dist)) + 1) % 3][
                           1]) / 2.0  # add something here
            self.save_robot((center_x, center_y), angle, 1)
        elif len(robot['blue']) == 1:
            angle = math.degrees(math.atan2(self.world.friend.orientation[0], self.world.friend.orientation[1]))
            self.save_robot((robot['blue'][0][0], robot['blue'][0][1]), angle, 1)
        else:
            angle = math.degrees(math.atan2(self.world.friend.orientation[0], self.world.friend.orientation[1]))
            self.save_robot((self.world.friend.position[0], self.world.friend.position[1]), angle, 1)

            # Enemy 1
            ######################################################################################################################

    def findEnemy1(self, robot):
        if len(robot['green']) == 1 and len(robot['yellow']) == 1:
            angle = math.degrees(math.atan2(robot['green'][0][0] - robot['yellow'][0][0],
                                            robot['green'][0][1] - robot['yellow'][0][1])) + self.single_angle
            self.save_robot((robot['yellow'][0][0], robot['yellow'][0][1]), angle, 2)
        elif len(robot['pink']) == 3:
            dist = []
            point_1 = []
            point_2 = []
            dist.append(sqrt(
                (robot['pink'][0][0] - robot['pink'][1][0]) ** 2 + (robot['pink'][0][1] - robot['pink'][1][1]) ** 2))

            dist.append(sqrt(
                (robot['pink'][1][0] - robot['pink'][2][0]) ** 2 + (robot['pink'][1][1] - robot['pink'][2][1]) ** 2))

            dist.append(sqrt(
                (robot['pink'][2][0] - robot['pink'][0][0]) ** 2 + (robot['pink'][2][1] - robot['pink'][0][1]) ** 2))

            point_1.append((robot['pink'][(dist.index(max(dist))) % 3][0] +
                            robot['pink'][(dist.index(max(dist)) + 1) % 3][0]) / 2.0)
            point_1.append((robot['pink'][(dist.index(max(dist))) % 3][1] +
                            robot['pink'][(dist.index(max(dist)) + 1) % 3][1]) / 2.0)
            point_2.append(robot['pink'][(dist.index(max(dist)) + 2) % 3][0])
            point_2.append(robot['pink'][(dist.index(max(dist)) + 2) % 3][1])
            angle = math.degrees(math.atan2(point_2[0] - point_1[0], point_2[1] - point_1[1])) + self.triple_angle
            center_x = (robot['pink'][(dist.index(max(dist))) % 3][0] + robot['pink'][(dist.index(max(dist)) + 1) % 3][
                0]) / 2.0  # add something here
            center_y = (robot['pink'][(dist.index(max(dist))) % 3][1] + robot['pink'][(dist.index(max(dist)) + 1) % 3][
                1]) / 2.0  # add something here
            self.save_robot((center_x, center_y), angle, 2)
        elif len(robot['yellow']) == 1:
            angle = math.degrees(math.atan2(self.world.enemy1.orientation[0], self.world.enemy1.orientation[1]))
            self.save_robot((robot['yellow'][0][0], robot['yellow'][0][1]), angle, 2)
        else:
            angle = math.degrees(math.atan2(self.world.enemy1.orientation[0], self.world.enemy1.orientation[1]))
            self.save_robot((self.world.enemy1.position[0], self.world.enemy1.position[1]), angle, 2)

            # enemy 2
            #######################################################################################################################

    def findEnemy2(self, robot):
        if len(robot['green']) == 1 and len(robot['yellow']) == 1:
            angle = math.degrees(math.atan2(robot['green'][0][0] - robot['yellow'][0][0],
                                            robot['green'][0][1] - robot['yellow'][0][1])) + self.single_angle
            self.save_robot((robot['yellow'][0][0], robot['yellow'][0][1]), angle, 3)
        elif len(robot['green']) == 3:
            dist = []
            point_1 = []
            point_2 = []
            dist.append(sqrt((robot['green'][0][0] - robot['green'][1][0]) ** 2 + (
            robot['green'][0][1] - robot['green'][1][1]) ** 2))

            dist.append(sqrt((robot['green'][1][0] - robot['green'][2][0]) ** 2 + (
            robot['green'][1][1] - robot['green'][2][1]) ** 2))

            dist.append(sqrt((robot['green'][2][0] - robot['green'][0][0]) ** 2 + (
            robot['green'][2][1] - robot['green'][0][1]) ** 2))

            point_1.append((robot['green'][(dist.index(max(dist))) % 3][0] +
                            robot['green'][(dist.index(max(dist)) + 1) % 3][0]) / 2.0)
            point_1.append((robot['green'][(dist.index(max(dist))) % 3][1] +
                            robot['green'][(dist.index(max(dist)) + 1) % 3][1]) / 2.0)
            point_2.append(robot['green'][(dist.index(max(dist)) + 2) % 3][0])
            point_2.append(robot['green'][(dist.index(max(dist)) + 2) % 3][1])
            angle = math.degrees(math.atan2(point_2[0] - point_1[0], point_2[1] - point_1[1])) + self.triple_angle
            center_x = (
                       robot['green'][(dist.index(max(dist))) % 3][0] + robot['green'][(dist.index(max(dist)) + 1) % 3][
                           0]) / 2.0  # add something here
            center_y = (
                       robot['green'][(dist.index(max(dist))) % 3][1] + robot['green'][(dist.index(max(dist)) + 1) % 3][
                           1]) / 2.0  # add something here
            self.save_robot((center_x, center_y), angle, 3)
        elif len(robot['yellow']) == 1:
            angle = math.degrees(math.atan2(self.world.enemy2.orientation[0], self.world.enemy2.orientation[1]))
            self.save_robot((robot['yellow'][0][0], robot['yellow'][0][1]), angle, 3)
        else:
            angle = math.degrees(math.atan2(self.world.enemy2.orientation[0], self.world.enemy2.orientation[1]))
            self.save_robot((self.world.enemy2.position[0], self.world.enemy2.position[1]), angle, 3)

    def save_robot(self, position, orientation, robot_id):
        robot = [self.world.venus, self.world.friend, self.world.enemy1, self.world.enemy2][robot_id]
        robot.position[0] = int(position[0])
        robot.position[1] = int(position[1])
        rad = math.radians(orientation)
        robot.orientation[0] = sin(rad)
        robot.orientation[1] = cos(rad)

    def findslope(self, point1, point2):
        numerator = point1[1] - point2[1]
        denominator = point1[0] - point2[0]  # sometimes it's not a point?? like [292. 292.]
        ans = (numerator, denominator)
        return ans

    def TrackCircle(self, color_name, color_ranges, imgOriginal, imgHSV):
        # self.trackstart = time.time()

        if len(color_ranges) == 2:
            imgThreshLow = cv2.inRange(imgHSV, color_ranges[0][0], color_ranges[0][1])
            imgThreshHigh = cv2.inRange(imgHSV, color_ranges[1][0], color_ranges[1][1])
            imgThresh = cv2.add(imgThreshLow, imgThreshHigh)
        else:
            imgThresh = cv2.inRange(imgHSV, color_ranges[0][0], color_ranges[0][1])

        # print "threshold combine", time.time() - self.trackstart
        # self.trackstart = time.time()

        imgThresh = cv2.GaussianBlur(imgThresh, (3, 3), 2)  # blur

        #print "gaussian", time.time() - self.trackstart
        #self.trackstart = time.time()

        # imgThresh = cv2.dilate(imgThresh, np.ones((5, 5), np.uint8))  # close image (dilate, then erode)
        # imgThresh = cv2.erode(imgThresh, np.ones((5, 5), np.uint8))  # closing "closes" (i.e. fills in) foreground gaps

        cv2.namedWindow(color_name, cv2.WINDOW_AUTOSIZE)
        cv2.imshow(color_name, imgThresh)

        # print "show window", time.time() - self.trackstart
        # self.trackstart = time.time()

        # intRows, intColumns = imgThresh.shape

        z = imgThresh

        # Label the clusters
        lw, num = measurements.label(z)

        # print "label", time.time() - self.trackstart
        # self.trackstart = time.time()

        # Calculate areas
        area = measurements.sum(z, lw, xrange(1, num + 1))

        # print "sum", time.time() - self.trackstart
        # self.trackstart = time.time()

        relevant_indices = area.argsort()[-MAX_COLOR_COUNTS[color_name]:]

        # print "relevant indices", time.time() - self.trackstart
        # self.trackstart = time.time()

        positions = []
        for index in relevant_indices:
            if area[index] > MIN_COLOR_AREA[color_name]:
                y, x = measurements.center_of_mass(z, lw, index=index + 1)
                positions.append((x, y, area[index], color_name))

        '''
        cluster = 1
        while cluster < len(area):
            y, x = measurements.center_of_mass(z, lw, index=cluster)

            # if self.debug:
            #    print obj.label + " " + str(int(pos[1])) +","+ str(int(pos[0]))

            positions.append((x, y))

            # cv2.circle(imgOriginal, (x,y), 3, (0, 255, 0), cv2.FILLED)

            # cv2.line(imgOriginal, (x,y),(0,0), (0, 255, 0), 2) # Trajectory drawn


            cluster = cluster + 1
            # area = np.delete(area, i)
        '''

        return positions
