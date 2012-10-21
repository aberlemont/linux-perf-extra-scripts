
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

class Events:
    def __init__(self):
        self._events = {}

    def append(self, other):
        cpu = other.cpu
        if cpu not in self._events:
            self._events[cpu] = []
        self._events[cpu].append(other)

    def sort(self):
        for cpu in self._events:
            self._events[cpu].sort(lambda a,b: cmp(a.nsecs, b.nsecs))

    def get_cpus(self):
        return self._events.keys()

    def get_events(self, cpu):
        return self._events[cpu]

# --- Latencies generation part ---

class Latencies:
    def __init__(self, names, limit, events = None, latencies = None):
        self.limit = limit
        if latencies is None:
            self._preset_names(names)
            self._preset_values(names, events)
        else:
            self.names = names
            self.latencies = [l[:] for l in latencies]

    def __add__(self, other):
        result = Latencies(self.names, self.limit, latencies = self.latencies)
        result += other
        return result

    def __iadd__(self, other):
        for i, values in enumerate(other.latencies):
            self.latencies[i] += values
        return self

    def __getitem__(self, name):
        index = self.names.index(name)
        return self.latencies[index]

    def _preset_names(self, names):
        # Set the latency names
        self.names = [names[i] + ' -> ' + names[i + 1] 
                      for i in xrange(len(names) - 1)] + ['total']

        # Build a map to translate event names to indexes
        names = [n.replace(':', '__') for n in names]
        self.name_to_index = dict((n, i) for i, n in enumerate(names))

    def _preset_values(self, names, events):
        events_count = len(names)
        self.latencies = [[] for i in xrange(events_count)]

        current_index = 0
        index_to_nsecs = {}

        for event in events:
            if event.name not in self.name_to_index.keys():
                continue

            # Get the index of the event according to the order
            # indicated by the user
            index = self.name_to_index[event.name]

            next_event = False
            next_cycle = True
            
            while not next_event:
                # If the events order is what we expected, we record
                # the current event's timestamp
                if index >= current_index:
                    index_to_nsecs[index] = event.nsecs
                    current_index = index + 1
                    next_event = True
                    next_cycle = False

                # If the order is not proper or we reach the end of a
                # cycle, let's compute the latencies
                if next_cycle or current_index == events_count:
                    self._compute_latencies(events_count, index_to_nsecs)
                    index_to_nsecs = {}
                    current_index = 0

        self._compute_latencies(events_count, index_to_nsecs)

    def _compute_latencies(self, events_count, times):
        # Here, we just retrieve a cycle of timestamps we will try to
        # convert into latencies
        indexes = times.keys()
        for i in xrange(events_count - 1):
            # If two events occured in the order we expected, we can
            # calculate the related latency
            if i in indexes and i + 1 in indexes:
                latency = times[i + 1] - times[i]
                if latency < config.limit:
                    self.latencies[i].append(latency)

        # If the first and last events' timestamps, we can get the
        # total latency
        if 0 in indexes and events_count - 1 in indexes:
            latency = times[events_count - 1] - times[0]
            if latency < config.limit:
                self.latencies[-1].append(latency)

# --- Latencies analysis part ---

class Statistics:
    def __init__(self, values = None):
        self.min = 1000000000
        self.max = 0
        self.sum = 0
        self.count = 0
        if values is not None:
            for value in values:
                self.update(value)

    def update(self, value):
        if value < self.min:
            self.min = value
        if value > self.max:
            self.max = value
        self.sum += value
        self.count += 1

    def get_values(self):
        result = (0 , 0, 0) if self.count == 0 else \
            (self.min, self.max, self.sum / self.count)
        return result

class Histogram:
    def __init__(self, values = None, bucket_size = 1000, buckets_count = 100):
        self.step = bucket_size
        self.count = buckets_count
        self.buckets = [i for i in xrange(self.count)]
        self.histo = [0 for i in xrange(self.count)]
        self.overflow = 0
        self.total = 0
        if values is not None:
            for value in values:
                self.update(value)

    def update(self, value):
        index = int(value / self.step)
        if index < self.count:
            self.histo[index] += 1
        else:
            self.overflow += 1
        self.total += 1

    def get_values(self):
        return self.histo

# --- Options management part ---

class Options:
    class Events:
        NAME = 'events='
        @staticmethod
        def check(arg):
            return arg[:len(Options.Events.NAME)] == Options.Events.NAME
        def __init__(self, arg):
            self.config = arg[len(Options.Events.NAME):].split(',')

    class Histo:
        NAME = 'histo'
        @staticmethod
        def check(arg):
            return arg[:len(Options.Histo.NAME)] == Options.Histo.NAME
        def __init__(self, arg):
            bucket = 1000
            count = 100
            name = Options.Histo.NAME + '='
            if arg[:len(name)] == name:
                _arg = arg[len(name):].split(',')
                if len(_arg) > 0:
                    bucket = int(_arg[0])
                if len(_arg) > 1:
                    count = int(_arg[1])

            self.config = (bucket, count)

    class Limit:
        NAME = 'limit='
        @staticmethod
        def check(arg):
            return arg[:len(Options.Limit.NAME)] == Options.Limit.NAME
        def __init__(self, arg):
            tmp = arg[len(Options.Limit.NAME):]
            self.config = int(tmp)

    def __init__(self, args):
        self.events = []
        self.histo = None
        self.limit = int(0xffffffffffffffff)

        for arg in args:
            if Options.Events.check(arg):
                self.events = Options.Events(arg).config
            elif Options.Histo.check(arg):
                self.histo = Options.Histo(arg).config
            elif Options.Limit.check(arg):
                self.limit = Options.Limit(arg).config
            else:
                raise ValueError('Unsupported options: ' + arg)

        if len(self.events) < 2:
            raise ValueError('Two events are needed at least')

# --- Report related part ---

def print_legend(latencies):
    names = latencies['all'].names

    print '# === Legend ==='
    legends = ['# L{:02d}: {}'.format(i, n) for i, n in enumerate(names)]
    for legend in legends:
        print legend
    
def print_stats(latencies):
    names = latencies['all'].names

    print '# === Statistics: min avg max (ns) ==='
    tmp = ['{:^23}'.format(k) for k in latencies.keys()]
    print '# cpus: ' + ' | '.join(tmp)

    for i, name in enumerate(names):
        values = [Statistics(latencies[k][name]).get_values() 
                  for k in latencies.keys()]
        tmp = ['{:07d} {:07d} {:07d}'.format(v[0], v[2], v[1]) for v in values]
        line = '{:^6}: '.format('L{:02d}'.format(i)) + ' | '.join(tmp)
        print line

def print_histograms(latencies, bucket, count):
    names = latencies['all'].names

    print '# === Histograms: bucket:{}ns ==='.format(bucket)

    for i, name in enumerate(names):
        tmp = ['{:^4}'.format(k) for k in latencies.keys()]
        print ' L{:02d} \ cpus: '.format(i) + ' | '.join(tmp)

        histograms = [Histogram(latencies[k][name], bucket, count) 
                      for k in latencies.keys()]
        
        values = [h.get_values() for h in histograms]
        overflows = [h.overflow for h in histograms]
        totals = [h.total for h in histograms]

        for i in xrange(count):
            tmp =  ['{:04d}'.format(v[i]) for v in values]
            line = '{:011d}: '.format(i * bucket) + ' | '.join(tmp)
            print line

        tmp =  ['{:04d}'.format(o) for o in overflows]
        line  = ' overflows : ' + ' | '.join(tmp)
        print line

        tmp =  ['{:04d}'.format(o) for o in totals]
        line  = '  totals   : ' + ' | '.join(tmp)
        print line

# --- Perf related part ---

events = None
config = None

def trace_unhandled(event_name, context, fields):
    args = (event_name, 
            context,
            fields['common_cpu'],
            Util.nsecs(fields['common_s'], fields['common_ns']),
            fields['common_pid'], fields['common_comm'])
    event = Event(*args)
    events.append(event)

def trace_begin():
    # Parse the script-specific options
    global config
    config = Options(sys.argv[1:])

    # Instanciate the global events holder
    global events
    events = Events()

def trace_end():
    # Here we sort the per-CPU events according to their timestamps
    events.sort()

    # For each CPU, we generate the latencies
    latencies = {}
    for cpu in events.get_cpus():
        _events = events.get_events(cpu)
        latencies[cpu] = Latencies(config.events, config.limit, _events)

    # Gather all the per-cpu latencies into a global set
    latencies['all'] = reduce(lambda a, b: a + b, latencies.values())

    # Print the results (according to the configuration)
    print_legend(latencies)
    print_stats(latencies)
    if config.histo is not None:
        print_histograms(latencies, *config.histo)

