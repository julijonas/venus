import time
import multiprocessing

import numpy as np
import math

from control.protocol import RobotProtocol
from strategy.simple_holonomic import SimpleStrategy
from strategy.highstrategy import StrategyTools
from strategy.world import World
from strategy.game import Game
from vision.vision import Vision

FRONT_RIGHT = 0
BACK_RIGHT = 1
BACK_LEFT = 2
FRONT_LEFT = 3
MOTOR_GRAB = 4
MOTOR_KICK = 5


def sign(x):
    return 1 if x >= 0 else -1


class Commands:
    def __init__(self):
        self.protocol = None
        self.vision_process = None
        self.world = None
        self.strategy = None
        self.highstrategy = None
        self.game = None
        print("! Remember to call:")
        print("! init <room: 0/1> <team_color: blue/yellow> <our_single_spot_color: green/pink>")
        print("! vision")
        print("! connect <device_no>")
        self.init()
        self.vision()
        self.connect()
        #self.highstrategy.main()

    def init(self, room_num=0, team_color='yellow', our_color='pink', computer_goal=False):
        print("init: Room: %s, team color: %s, our single spot color: %s, computer goal: %s" %
              (room_num, team_color, our_color, computer_goal))
        self.world = World(int(room_num), team_color, our_color, computer_goal)
        self.strategy = SimpleStrategy(self.world, self)
        self.game = Game(self.world, self)
        self.highstrategy = StrategyTools(self.world, self, self.game, self.strategy)

    def connect(self, device_no='0'):
        print("connect: Connecting to RF stick")
        self.protocol = RobotProtocol('/dev/ttyACM' + device_no)

    def vision(self):
        if not self.vision_process:
            print("vision: Starting vision")
            self.vision_process = multiprocessing.Process(target=Vision, args=(self.world,))
            self.vision_process.start()

    def map(self, state):
        self.game.mid(state, True)

    def test(self, state):
        while True:
            self.game.mid(state, False)

    def move(self, direction, angle): # direction is between our orientation and where we want to go
        dir = int(direction)
        ang = int(angle)
        if dir < 0:
            d = 45 - dir
        else:
            d = -(dir - 45)

        a = -math.radians(ang)
        dir = math.radians(d)
        idea = np.array([np.cos(dir), np.sin(dir), a])
        rad = 0.1
        m = np.array([[1, 0, rad],
                      [0, -1, rad],
                      [-1, 0, rad],
                      [0, 1, rad]])

        movement = np.dot(m, idea)
        sizes = np.fabs(movement)
        factor = np.amax(sizes)
        movement = np.multiply(100.0/factor, movement)

        movement = movement.round()
        print movement
        self.protocol.move_forever([(0, int(movement[0])), (1, int(movement[1])), (2, int(movement[2])), (3, int(movement[3])), ])
        #self.protocol.move(20, [(0, movement[0]), (1, movement[1]), (2, movement[2]), (3, movement[3]), ], wait=True)

    def f(self, x):
        """Move forward, negative x means backward"""
        x = int(x)
        s = sign(x)
        x = abs(x)
        # Calibrated for the holonomic robot on 27 March, only forward
        x = 5.3169850194 * x - 14.9575723714
        x = int(x)
        if x > 0:
            self.protocol.move(x, [(0, 100 * s), (1, -100 * s), (2, -100 * s), (3, 100 * s)], wait=True)

    def c(self, x):
        """Rotate clockwise, negative x means counter-clockwise"""
        x = int(x)
        s = sign(x)
        x = abs(x)

        # Calibrated for the holonomic robot on 27 March
        if x > 90:
            x = 0.8133333333 * x - 29.0
        else:
            x = 0.0028306977 * (x ** 2) + 0.2889794061 * x
        x = int(x)

        if x > 0:
            self.protocol.move(x, [(0, -90 * s), (1, -90 * s), (2, -90 * s), (3, -90 * s)], wait=True)

    def s(self):
        self.protocol.stop()

    def k(self):
        # self.protocol.move(500, [(4, -100)], time=True)
        self.protocol.move_forever([(0, -100), (1, 100), (2, 100), (3, -100), ])
        time.sleep(0.5)
        self.protocol.move_forever([(0, 100), (1, -100), (2, -100), (3, 100), ])
        time.sleep(1)
        self.protocol.stop()

    def o(self):
        self.protocol.move(400, [(4, -100)], time=True, wait=True)

    def g(self):
        self.protocol.move(400, [(4, 80)], time=True, wait=True)

    def ss(self, x):
        x = int(x)
        s = sign(x)
        x = abs(x)

        if x < 90:
            return

        if x > 90:
            if s > 0:
                x = 0.0008417761 * (x ** 2) + 0.3865014241 * x - 41.5767918089
            else:
                x = 0.0013813605 * (x ** 2) + 0.1536110506 * x - 25.1058020478
            x = int(x)
            self.protocol.schedule(x, 0, [(0, -100 * s), (1, -100 * s), (2, -100 * s), (3, -100 * s)])

        self.protocol.schedule(200, 0, [(0, -100 * s), (1, -100 * s), (2, -100 * s), (3, -100 * s)], grab=-400)

        #self.protocol.move(400, [(4, -100)], time=True)

    def flush(self):
        self.protocol.flush()

    def ee(self, x):
        x = int(x)
        s = sign(x)
        self.protocol.move(400, [(4, -100)], time=True)
        self.protocol.move(100, [(0, -100 * s), (1, -100 * s), (2, -100 * s), (3, -100 * s)], wait=True)

    def w(self):
        print self.world

    def query_ball(self):
        a = self.protocol.query_ball()
        print("We have the ball: %s" % a)
        return a

    def pass_ball(self):
        self.strategy.pass_ball()

    def catch_ball(self):
        self.strategy.catch_ball()

    def goal(self):
        self.strategy.goal()
