
import os
import sys

sys.path.append(os.environ['PERF_EXEC_PATH'] + \
	'/scripts/python/Perf-Trace-Util/lib/Perf/Trace')

import Util 

# --- Events management part ---

class Event:
    ARGS = ('name', 'context', 'cpu', 'nsecs', 'pid', 'comm')

    def __init__(self, *args, **keywords):
        # Basic checking
        assert len(args) == len(Event.ARGS)

        # Set the mandatory arguments...
        for i, arg in enumerate(Event.ARGS):
            setattr(self, arg, args[i])

        # ...and the optional ones (one never knows)
        for key, value in keywords.iteritems():
            setattr(self, key, value)

# --- Timeslot generation part ---

class Timeslot:
    def __init__(self):
        self.counts = {}

    def __getitem__(self, key):
        return self.counts[key] if key in self.counts else 0

    def append(self, event):
        key = (event.cpu, event.name)
        self.counts[key] = self.counts.get(key, 0) + 1
        key = ('all', event.name)
        self.counts[key] = self.counts.get(key, 0) + 1

    def keys(self):
        return self.counts.keys()

    def cpus(self):
        return set([k[0] for k in self.counts.keys()])

class Timeslots:
    def __init__(self, slot_nsecs):
        self.slot_nsecs = slot_nsecs
        self.timeslots = {}

    def __getitem__(self, key):
        return self.timeslots[key]

    def append(self, event):
        index = event.nsecs / self.slot_nsecs
        tmp = self.timeslots.get(index, Timeslot())
        tmp.append(event)
        self.timeslots[index] = tmp

    def keys(self):
        return self.timeslots.keys()

# --- Options management part ---

class Options:
    class Events:
        NAME = 'events='
        @staticmethod
        def check(arg):
            return arg[:len(Options.Events.NAME)] == Options.Events.NAME
        def __init__(self, arg):
            self.config = arg[len(Options.Events.NAME):].split(',')

    class Slot:
        NAME = 'slot='
        @staticmethod
        def check(arg):
            return arg[:len(Options.Slot.NAME)] == Options.Slot.NAME
        def __init__(self, arg):
            self.config = int(arg[len(Options.Slot.NAME):])

    def __init__(self, args):
        self.events = []
        self.slot_nsecs = 100000 # 100us

        for arg in args:
            if Options.Events.check(arg):
                self.events = Options.Events(arg).config
            elif Options.Slot.check(arg):
                self.slot_nsecs = Options.Slot(arg).config
            else:
                raise ValueError('Unsupported options: ' + arg)

        if len(self.events) < 1:
            raise ValueError('One event is needed at least')

# --- Report related part ---

def print_legend():
    print '# === Legend ==='
    for i, name in enumerate(config.events):
        line = '# E{:02d}: '.format(i) + name
        print line

def print_timeslots(timeslots):
    print '# === Timeslots (slot duration: {}ns) ==='.format(config.slot_nsecs)
    
    indexes = timeslots.keys()
    # Theoretically, the sort is useless, here
    indexes.sort()

    names = [e.replace(':', '__') for e in config.events]

    cpus = set()
    for index in indexes:
        cpus |= timeslots[index].cpus()

    cpu_format = '{:^SIZE}'.replace('SIZE', str(len(names) * 4 - 1))
    cpus_strings = [cpu_format.format(i) for i in cpus]
    print '#  cpus   : ' + ' | '.join(cpus_strings)

    names_strings = ['E{:02d}'.format(i) for i, _ in enumerate(names)]
    names_strings =  ' '.join(names_strings)
    names_strings = [names_strings] * len(cpus)
    print '# ns\evts : ' + ' | '.join(names_strings)

    for index in indexes:
        slot = timeslots[index]
        percpu_counts = []

        for cpu in cpus:
            tmp = [slot[(cpu, n)] for n in names]
            tmp = ' '.join(['{:03d}'.format(t) for t in tmp])
            percpu_counts.append(tmp)

        nsecs = (index - indexes[0]) * config.slot_nsecs
        line = '{:010d}: '.format(nsecs)
        line += ' | '.join(percpu_counts)
        print line

# --- Perf related part ---

timeslots = None
config = None

def trace_unhandled(event_name, context, fields):
    args = (event_name, 
            context,
            fields['common_cpu'],
            Util.nsecs(fields['common_s'], fields['common_ns']),
            fields['common_pid'], fields['common_comm'])
    event = Event(*args)
    timeslots.append(event)

def trace_begin():
    # Parse the script-specific options
    global config
    config = Options(sys.argv[1:])

    # Instanciate the global events holder
    global timeslots
    timeslots = Timeslots(config.slot_nsecs)

def trace_end():
    print_legend()
    print_timeslots(timeslots)

    
