
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

# --- Counting part ---

class Counts:
    def __init__(self, names, events = None, counts = None):
        if counts is None:
            self._preset_names(names)
            self._preset_values(names, events)
        else:
            self.names = names
            self.counts = [c[:] for c in counts]

    def __add__(self, other):
        result = Counts(self.names, counts = self.counts)
        result += other
        return result

    def __iadd__(self, other):
        for i, values in enumerate(other.counts):
            self.counts[i] += values
        return self        

    def __getitem__(self, name):
        index = self.names.index(name)
        return self.counts[index]

    def _preset_names(self, names):
        self.edges = [names[0], names[-1]]
        self.names = names[1 : -1]

        self._edges = [n.replace(':', '__') for n in self.edges]
        self._names = [n.replace(':', '__') for n in self.names]
        
    def _preset_values(self, names, events):
        # Build a map to translate event names to indexes
        self.name_to_index = dict((n, i) for i, n in enumerate(self._names))

        record = False
        counts = None
        all_counts = []

        for event in events:
            if event.name == self._edges[0]:
                counts = [0 for _ in self.names]
                record = True
            elif event.name == self._edges[1]:
                all_counts.append(counts)
                counts = None
                record = False
            elif record and event.name in self.name_to_index:
                index = self.name_to_index[event.name]
                counts[index] += 1

        if len(all_counts) == 0:
            all_counts.append([0] * len(self.names))

        self.counts = zip(*all_counts)

# --- Counts analysis part ---

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
            bucket = 10
            count = 20
            name = Options.Histo.NAME + '='
            if arg[:len(name)] == name:
                _arg = arg[len(name):].split(',')
                if len(_arg) > 0:
                    bucket = int(_arg[0])
                if len(_arg) > 1:
                    count = int(_arg[1])

            self.config = (bucket, count)

    def __init__(self, args):
        self.events = []
        self.histo = None

        for arg in args:
            if Options.Events.check(arg):
                self.events = Options.Events(arg).config
            elif Options.Histo.check(arg):
                self.histo = Options.Histo(arg).config
            else:
                raise ValueError('Unsupported options: ' + arg)

        if len(self.events) < 3:
            raise ValueError('Three events are needed at least')

# --- Report related part ---

def print_legend(counts):
    names = counts['all'].names

    print '# === Legend ==='
    legends = ['# E{:02d}: {}'.format(i, n) for i, n in enumerate(names)]
    for legend in legends:
        print legend
    
def print_stats(counts):
    names = counts['all'].names

    print '# === Statistics: min avg max (ns) ==='
    tmp = ['{:^23}'.format(k) for k in counts.keys()]
    print '# cpus: ' + ' | '.join(tmp)

    for i, name in enumerate(names):
        values = [Statistics(counts[k][name]).get_values() 
                  for k in counts.keys()]
        tmp = ['{:07d} {:07d} {:07d}'.format(v[0], v[2], v[1]) for v in values]
        line = '{:^6}: '.format('E{:02d}'.format(i)) + ' | '.join(tmp)
        print line

def print_histograms(counts, bucket, count):
    names = counts['all'].names

    print '# === Histograms: bucket:{} ==='.format(bucket)

    for i, name in enumerate(names):
        tmp = ['{:^4}'.format(k) for k in counts.keys()]
        print ' E{:02d} \ cpus: '.format(i) + ' | '.join(tmp)

        histograms = [Histogram(counts[k][name], bucket, count) 
                      for k in counts.keys()]
        
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

    # For each CPU, we generate the counts
    counts = {}
    for cpu in events.get_cpus():
        _events = events.get_events(cpu)
        counts[cpu] = Counts(config.events, _events)

    # Gather all the per-cpu counts into a global set
    counts['all'] = reduce(lambda a, b: a + b, counts.values())

    # Print the results (according to the configuration)
    print_legend(counts)
    print_stats(counts)
    if config.histo is not None:
        print_histograms(counts, *config.histo)

