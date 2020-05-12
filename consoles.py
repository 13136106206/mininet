#!/usr/bin/python

"""
consoles.py: bring up a bunch of miniature consoles on a virtual network

This demo shows how to monitor a set of nodes by using
Node's monitor() and Tkinter's createfilehandler().

We monitor nodes in a couple of ways:

- First, each individual node is monitored, and its output is added
  to its console window

- Second, each time a console window gets iperf output, it is parsed
  and accumulated. Once we have output for all consoles, a bar is
  added to the bandwidth graph.

The consoles also support limited interaction:

- Pressing "return" in a console will send a command to it

- Pressing the console's title button will open up an xterm

Bob Lantz, April 2010

"""
import time
import re

from Tkinter import Frame, Button, Label, Text, Scrollbar, Canvas, Wm, READABLE

from mininet.log import setLogLevel
from mininet.topolib import TreeNet
from mininet.term import makeTerms, cleanUpScreens
from mininet.util import quietRun
from mininet.node import Node
from mininet.topo import Topo
from mininet.net import Mininet

servers = 2
nathost = 1
clients = 4
global start_how_many
start_how_many = 1


class MyNode(Node):
    def __init__(self):
        Node.__init__(self)


class MyTopo(Topo):
    "Simple topology example."

    def __init__(self):
        "Create custom topo."

        # Initialize topology
        Topo.__init__(self)

        # Add hosts and switches
        s1 = self.addSwitch('s1')
        for i in range(1, servers + clients + 1):
            mac = hex(i).replace('0x', '')
            mac = '0' * (12 - len(mac)) + mac
            for j in range(5, 0, -1):
                mac = mac[0: j * 2] + ':' + mac[j * 2: len(mac)]
            exec ("br500_" + str(i) + "= self.addHost('br500_" + str(i) + "', mac='" + mac + "')")
            exec ("self.addLink(s1" + ", br500_" + str(i) + ")")


topos = {'mytopo': (lambda: MyTopo())}


class Console(Frame):
    "A simple console on a host."

    def __init__(self, parent, net, node, height=10, width=32, title='Node'):
        Frame.__init__(self, parent)

        self.net = net
        self.node = node
        self.prompt = node.name + '# '
        self.height, self.width, self.title = height, width, title

        # Initialize widget styles
        self.buttonStyle = {'font': 'Monaco 14'}
        self.textStyle = {
            'font': 'Monaco 14',
            'bg': 'black',
            'fg': 'green',
            'width': self.width,
            'height': self.height,
            'relief': 'sunken',
            'insertbackground': 'green',
            'highlightcolor': 'green',
            'selectforeground': 'black',
            'selectbackground': 'green'
        }

        # Set up widgets
        self.text = self.makeWidgets()
        self.bindEvents()
        self.sendCmd('export TERM=dumb')

        self.outputHook = None

    def makeWidgets(self):
        "Make a label, a text area, and a scroll bar."

        def newTerm(net=self.net, node=self.node, title=self.title):
            "Pop up a new terminal window for a node."
            net.terms += makeTerms([node], title)

        label = Button(self, text=self.node.name, command=newTerm,
                       **self.buttonStyle)
        label.pack(side='top', fill='x')
        text = Text(self, wrap='word', **self.textStyle)
        ybar = Scrollbar(self, orient='vertical', width=7,
                         command=text.yview)
        text.configure(yscrollcommand=ybar.set)
        text.pack(side='left', expand=True, fill='both')
        ybar.pack(side='right', fill='y')
        return text

    def bindEvents(self):
        "Bind keyboard and file events."
        # The text widget handles regular key presses, but we
        # use special handlers for the following:
        self.text.bind('<Control-c>', self.handlec)
        self.text.bind('<Control-v>', self.handlev)
        self.text.bind('<Return>', self.handleReturn)
        self.text.bind('<Control-d>', self.handleInt)
        self.text.bind('<KeyPress>', self.handleKey)

        # This is not well-documented, but it is the correct
        # way to trigger a file event handler from Tk's
        # event loop!
        self.tk.createfilehandler(self.node.stdout, READABLE,
                                  self.handleReadable)

    # We're not a terminal (yet?), so we ignore the following
    # control characters other than [\b\n\r]
    ignoreChars = re.compile(r'[\x00-\x07\x09\x0b\x0c\x0e-\x1f]+')

    def append(self, text):
        "Append something to our text frame."
        text = self.ignoreChars.sub('', text)
        self.text.insert('end', text)
        self.text.mark_set('insert', 'end')
        self.text.see('insert')
        outputHook = lambda x, y: True  # make pylint happier
        if self.outputHook:
            outputHook = self.outputHook
        outputHook(self, text)

    def handlec(self, event):
        if self.node.waiting:
            self.node.write(event.char)

    def handlev(self, event):
        if self.node.waiting:
            self.node.write(event.char)

    def handleKey(self, event):
        "If it's an interactive command, send it to the node."
        char = event.char
        if self.node.waiting:
            self.node.write(char)

    def handleReturn(self, event):
        "Handle a carriage return."
        cmd = self.text.get('insert linestart', 'insert lineend')
        # Send it immediately, if "interactive" command
        if self.node.waiting:
            self.node.write(event.char)
            return
        # Otherwise send the whole line to the shell
        pos = cmd.find(self.prompt)
        if pos >= 0:
            cmd = cmd[pos + len(self.prompt):]
        self.sendCmd(cmd)

    # Callback ignores event
    def handleInt(self, _event=None):
        "Handle control-c."
        self.node.sendInt()

    def sendCmd(self, cmd):
        "Send a command to our node."
        if not self.node.waiting:
            self.node.sendCmd(cmd)

    def handleReadable(self, _fds, timeoutms=None):
        "Handle file readable event."
        data = self.node.monitor(timeoutms)
        self.append(data)
        if not self.node.waiting:
            # Print prompt
            self.append(self.prompt)

    def waiting(self):
        "Are we waiting for output?"
        return self.node.waiting

    def waitOutput(self):
        "Wait for any remaining output."
        while self.node.waiting:
            # A bit of a trade-off here...
            self.handleReadable(self, timeoutms=1000)
            self.update()

    def clear(self):
        "Clear all of our text."
        self.text.delete('1.0', 'end')


class Graph(Frame):
    "Graph that we can add bars to over time."

    def __init__(self, parent=None, bg='white', gheight=200, gwidth=500,
                 barwidth=10, ymax=3.5, ):

        Frame.__init__(self, parent)
        self.bg = bg
        self.gheight = gheight
        self.gwidth = gwidth
        self.barwidth = barwidth
        self.ymax = float(ymax)
        self.xpos = 0

        # Create everything
        self.title, self.scale, self.graph = self.createWidgets()
        self.updateScrollRegions()
        self.yview('moveto', '1.0')

    def createScale(self):
        "Create a and return a new canvas with scale markers."
        height = float(self.gheight)
        width = 25
        ymax = self.ymax
        scale = Canvas(self, width=width, height=height,
                       background=self.bg)
        opts = {'fill': 'red'}
        # Draw scale line
        scale.create_line(width - 1, height, width - 1, 0, **opts)
        # Draw ticks and numbers
        for y in range(0, int(ymax + 1)):
            ypos = height * (1 - float(y) / ymax)
            scale.create_line(width, ypos, width - 10, ypos, **opts)
            scale.create_text(10, ypos, text=str(y), **opts)
        return scale

    def updateScrollRegions(self):
        "Update graph and scale scroll regions."
        ofs = 20
        height = self.gheight + ofs
        self.graph.configure(scrollregion=(0, -ofs,
                                           self.xpos * self.barwidth, height))
        self.scale.configure(scrollregion=(0, -ofs, 0, height))

    def yview(self, *args):
        "Scroll both scale and graph."
        self.graph.yview(*args)
        self.scale.yview(*args)

    def createWidgets(self):
        "Create initial widget set."

        # Objects
        title = Label(self, text='Bandwidth (Gb/s)', bg=self.bg)
        width = self.gwidth
        height = self.gheight
        scale = self.createScale()
        graph = Canvas(self, width=width, height=height, background=self.bg)
        xbar = Scrollbar(self, orient='horizontal', command=graph.xview)
        ybar = Scrollbar(self, orient='vertical', command=self.yview)
        graph.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set,
                        scrollregion=(0, 0, width, height))
        scale.configure(yscrollcommand=ybar.set)

        # Layout
        title.grid(row=0, columnspan=3, sticky='new')
        scale.grid(row=1, column=0, sticky='nsew')
        graph.grid(row=1, column=1, sticky='nsew')
        ybar.grid(row=1, column=2, sticky='ns')
        xbar.grid(row=2, column=0, columnspan=2, sticky='ew')
        self.rowconfigure(1, weight=1)
        self.columnconfigure(1, weight=1)
        return title, scale, graph

    def addBar(self, yval):
        "Add a new bar to our graph."
        percent = yval / self.ymax
        c = self.graph
        x0 = self.xpos * self.barwidth
        x1 = x0 + self.barwidth
        y0 = self.gheight
        y1 = (1 - percent) * self.gheight
        c.create_rectangle(x0, y0, x1, y1, fill='green')
        self.xpos += 1
        self.updateScrollRegions()
        self.graph.xview('moveto', '1.0')

    def clear(self):
        "Clear graph contents."
        self.graph.delete('all')
        self.xpos = 0

    def test(self):
        "Add a bar for testing purposes."
        ms = 1000
        if self.xpos < 10:
            self.addBar(self.xpos / 10 * self.ymax)
            self.after(ms, self.test)

    def setTitle(self, text):
        "Set graph title"
        self.title.configure(text=text, font='Helvetica 9 bold')


class ConsoleApp(Frame):
    "Simple Tk consoles for Mininet."

    menuStyle = {'font': 'Geneva 7 bold'}

    def __init__(self, net, parent=None, width=4):
        Frame.__init__(self, parent)
        self.top = self.winfo_toplevel()
        self.gheight = 800
        self.top.title('Mininet')
        self.net = net
        self.menubar = self.createMenuBar()
        self.consoles = {}

        self.sconsoles = {}  # consoles themselves
        titles = {
            'hosts': 'Host',
            'switches': 'Switch',
            'controllers': 'Controller'
        }
        # (servers + clients) * 20

        canvas = self.canvas = Canvas(self, width=1600, height=800,
                                      scrollregion=(0, 0, 0, ((servers + nathost + clients + 8) // 4) * 264))

        # cframe = self.cframe = Frame(canvas, width=1600, height=((servers + nathost + clients + 3) // 4) * 264)
        cframe = self.cframe = Frame(canvas)
        for name in titles:
            nodes = getattr(net, name)
            frame, consoles = self.createConsoles(
                cframe, nodes, width, titles[name])
            self.consoles[name] = Object(frame=frame, consoles=consoles)
        canvas.create_window((800, ((servers + nathost + clients + 12) // 4) * 132), window=cframe)
        self.selected = None
        self.select('hosts')

        ybar = Scrollbar(self, orient='vertical', command=canvas.yview)
        canvas.config(yscrollcommand=ybar.set)

        ybar.pack(side='right', fill='y')
        canvas.pack(expand=True, fill='both')

        cleanUpScreens()
        # Close window gracefully
        Wm.wm_protocol(self.top, name='WM_DELETE_WINDOW', func=self.quit)

        # Initialize graph
        graph = Graph(cframe)
        self.consoles['graph'] = Object(frame=graph, consoles=[graph])
        self.graph = graph
        self.graphVisible = False
        self.updates = 0
        self.hostCount = len(self.consoles['hosts'].consoles)
        self.bw = 0

        self.pack(expand=True, fill='both')

    def updateGraph(self, _console, output):
        "Update our graph."
        m = re.search(r'(\d+.?\d*) ([KMG]?bits)/sec', output)
        if not m:
            return
        val, units = float(m.group(1)), m.group(2)
        # convert to Gbps
        if units[0] == 'M':
            val *= 10 ** -3
        elif units[0] == 'K':
            val *= 10 ** -6
        elif units[0] == 'b':
            val *= 10 ** -9
        self.updates += 1
        self.bw += val
        if self.updates >= self.hostCount:
            self.graph.addBar(self.bw)
            self.bw = 0
            self.updates = 0

    def setOutputHook(self, fn=None, consoles=None):
        "Register fn as output hook [on specific consoles.]"
        if consoles is None:
            consoles = self.consoles['hosts'].consoles
        for console in consoles:
            console.outputHook = fn

    def createConsoles(self, parent, nodes, width, title):
        "Create a grid of consoles in a frame."
        f = Frame(parent)
        # Create consoles
        consoles = []
        index = 0
        for node in nodes:
            console = Console(f, self.net, node, title=title)
            consoles.append(console)
            row = index / width
            column = index % width
            console.grid(row=row, column=column, sticky='nsew')
            index += 1
            f.rowconfigure(row)
            f.columnconfigure(column, weight=1)
        return f, consoles

    def select(self, groupName):
        "Select a group of consoles to display."
        if self.selected is not None:
            self.selected.frame.pack_forget()
        self.selected = self.consoles[groupName]
        self.selected.frame.pack(expand=True, fill='both')

    def createMenuBar(self):
        "Create and return a menu (really button) bar."
        f = Frame(self)
        buttons = [
            ('Hosts', lambda: self.select('hosts')),
            ('Switches', lambda: self.select('switches')),
            ('Controllers', lambda: self.select('controllers')),
            ('Graph', lambda: self.select('graph')),
            ('iptablse', self.iptablse),
            ('mqtt_ctrl', self.mqtt_ctrl),
            ('vppn_ctrl', self.vppn_ctrl),
            ('Debug', self.debug),
            ('Stop_tinc', self.stoptinc),
            ('Ping', self.ping),
            ('iperf_serv', self.iperf_serv),
            ('iperf_cent', self.iperf_cent),
            ('iperf_stop', self.iperf_stop),
            ('Interrupt', self.stop),
            ('Clear', self.clear),
            ('Quit', self.quit)
        ]
        for name, cmd in buttons:
            b = Button(f, text=name, command=cmd, **self.menuStyle)
            b.pack(side='left')
        f.pack(padx=4, pady=4, fill='x')
        return f

    def clear(self):
        "Clear selection."
        for console in self.selected.consoles:
            console.clear()

    def waiting(self, consoles=None):
        "Are any of our hosts waiting for output?"
        if consoles is None:
            consoles = self.consoles['hosts'].consoles
        for console in consoles:
            if console.waiting():
                return True
        return False

    def mqtt_ctrl(self):
        consoles = self.consoles['hosts'].consoles
        if self.waiting(consoles):
            return
        i = 0
        for console in consoles:
            i += 1
            if i <= servers + clients:
                console.sendCmd('mqtt-client -c ' + str(i - 1) + ' -n -f -u routertestuser -p 123456 &')

    def vppn_ctrl(self):
        consoles = self.consoles['hosts'].consoles
        if self.waiting(consoles):
            return
        i = 0
        for console in consoles:
            i += 1
            if i <= servers + clients:
                console.sendCmd('vppnctrl -t ' + str(i - 1) + ' run')

    def debug(self):
        consoles = self.consoles['hosts'].consoles
        if self.waiting(consoles):
            return
        i = 0
        for console in consoles:
            i += 1

            #if i <= servers + clients:
            #global start_how_many
            #if start_how_many <= i < start_how_many + 10:
	    if i > 1 :
                console.sendCmd('sudo /etc/tinc/' + str(i) + '/start &')
		#sudo tincd -c /etc/tinc/' + str(i) + ' --pidfile=/etc/tinc/' + str(i) + "/tinc.pid -D -d 1 &")
        #start_how_many = start_how_many + 10

    def stoptinc(self):
        os.system('killall tincd')
        #global start_how_many
        #if start_how_many > 10:
        #    for i in range(start_how_many - 10, start_how_many + 1):
        #        os.system('sudo /root/tinc/tinc -c /etc/tinc/' + str(i) + ' --pidfile=/etc/tinc/' + str(i) + "/tinc.pid stop")
        #    start_how_many = start_how_many - 10

    def iptablse(self):
        if clients > 1:
            consoles = self.consoles['hosts'].consoles
            if self.waiting(consoles):
                return
            i = 0
            for console in consoles:
                i += 1
                if servers < i <= servers + clients:
                    if i == servers:
                        console.sendCmd('iptables -A OUTPUT -m iprange --dst-range 10.0.0.' + str(
                            servers + 2) + '-10.0.0.' + str(servers + clients) + ' -j DROP')
                    elif i == servers + clients:
                        console.sendCmd('iptables -A OUTPUT -m iprange --dst-range 10.0.0.' + str(
                            servers + 1) + '-10.0.0.' + str(servers + clients - 1) + ' -j DROP')
                    else:
                        console.sendCmd('iptables -A OUTPUT -m iprange --dst-range 10.0.0.' + str(
                            servers + 1) + '-10.0.0.' + str(i) + ' -j DROP')
                        time.sleep(0.001)
                        console.sendCmd(
                            'iptables -A OUTPUT -m iprange --dst-range 10.0.0.' + str(i + 1) + '-10.0.0.' + str(
                                servers + clients) + ' -j DROP')

    def ping(self):
        "Tell each host to ping the next one."
        consoles = self.consoles['hosts'].consoles
        if self.waiting(consoles):
            return
        count = len(consoles)

        i = 0
        for console in consoles:
            i += 1
            if servers < i <= servers + clients:
                if i == count - nathost:
                    j = servers
                else:
                    j = i
                ip = '10.1.0.' + str(j + 1)
                console.sendCmd('ping ' + ip)

    def iperf_serv(self):
        "Tell each host to iperf to the next one."
        consoles = self.consoles['hosts'].consoles
        if self.waiting(consoles):
            return
        count = len(consoles)
        self.setOutputHook(self.updateGraph)
        # for console in consoles:
        # Sometimes iperf -sD doesn't return,
        # so we run it in the background instead
        # console.handleReturn()
        i = 1
        for console in consoles:
            i += 1
            if servers < i <= servers + clients:
                if i == count - nathost:
                    j = servers
                else:
                    j = i
                ip = '10.1.0.' + str(j)
                console.sendCmd('iperf -t 99999 -i 1 -s ' + ip + ' &')

    def iperf_cent(self):
        "Tell each host to iperf to the next one."
        consoles = self.consoles['hosts'].consoles
        if self.waiting(consoles):
            return
        count = len(consoles)
        self.setOutputHook(self.updateGraph)
        # for console in consoles:
        # Sometimes iperf -sD doesn't return,
        # so we run it in the background instead
        # console.handleReturn()

        i = 0
        for console in consoles:
            i += 1
            if servers < i <= servers + clients:
                if i == count - nathost:
                    j = servers
                else:
                    j = i
                ip = '10.1.0.' + str(j + 1)
                console.sendCmd('iperf -t 99999 -i 1 -c ' + ip)

    def iperf_stop(self, wait=True):
        quietRun('killall -9 iperf')

    def stop(self, wait=True):
        "Interrupt all hosts."
        consoles = self.consoles['hosts'].consoles
        for console in consoles:
            console.handleInt()
        if wait:
            for console in consoles:
                console.waitOutput()
        self.setOutputHook(None)
        # Shut down any iperfs that might still be running
        quietRun('killall -9 iperf')

    def quit(self):
        "Stop everything and quit."
        self.stop(wait=False)
        Frame.quit(self)


# Make it easier to construct and assign objects

def assign(obj, **kwargs):
    "Set a bunch of fields in an object."
    obj.__dict__.update(kwargs)


class Object(object):
    "Generic object you can stuff junk into."

    def __init__(self, **kwargs):
        assign(self, **kwargs)


if __name__ == '__main__':
    import os

    os.system('mn -c')
    setLogLevel('info')
    network = Mininet(MyTopo())

    network.addNAT().configDefault()
    network.start()
    app = ConsoleApp(network, width=4)
    # Add NAT connectivity

    app.mainloop()

    network.stop()

