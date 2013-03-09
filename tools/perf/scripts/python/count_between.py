
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
    SIZE_THRESHOLD = 1024
    LEFT_THRESHOLD = 128

    def __init__(self, config):
        self._config = config
        self._events = {}
        self._counts = {}
        self._statistics = {}
        self._histograms = {} if self._config.histo else None

    def _add_cpu(self, cpu):
        # ...so, for each cpu, we create a simple events
        # container...
        self._events[cpu] = []

        # ...a counts processing instance...
        self._counts[cpu] = Counts(self._config.events)

        # ...a statistics processing instance...
        self._statistics[cpu] = dict([(n, Statistics()) 
                                      for n in self._counts[cpu].names])

        # ...and a histogram instance
        if self._config.histo:
            self._histograms[cpu] = dict([(n, Histogram(*self._config.histo)) 
                                          for n in self._counts[cpu].names])

    def _process_counts(self, cpu, events):
        for event in events:
            self._counts[cpu].update(event)

        for _name, _counts in self._counts[cpu].getitems().iteritems():
            _statistics = self._statistics[cpu][_name]
            for _count in _counts:
                _statistics.update(_count)

            if self._config.histo:
                _histogram = self._histograms[cpu][_name]
                for _count in _counts:
                    _histogram.update(_count)
        
    def append(self, other):
        cpu = other.cpu
        # To prevent tricky cpu detection code, cpus are discovered
        # through the events...
        if cpu not in self._events:
            self._add_cpu(cpu)

        self._events[cpu].append(other)

        if len(self._events[cpu]) > Events.SIZE_THRESHOLD:
            self._events[cpu].sort(lambda a,b: cmp(a.nsecs, b.nsecs))
            
            events_subset = self._events[cpu][:-Events.LEFT_THRESHOLD]
            self._process_counts(cpu, events_subset)

            self._events[cpu] = self._events[cpu][-Events.LEFT_THRESHOLD:]

    def flush(self):
        for cpu in self._events.keys():
            self._events[cpu].sort(lambda a,b: cmp(a.nsecs, b.nsecs))
            self._process_counts(cpu, self._events[cpu])
            self._events[cpu] = []

    def get_names(self):
        if len(self._counts) == 0:
            raise ValueError('No events detected')
        first_key = self._counts.keys()[0]
        return self._counts[first_key].names
                    
    def get_cpus(self):
        return self._events.keys() + ['all']

    def get_statistics(self, cpu, name):
        if cpu == 'all':
            all_stats = [self._statistics[c][name] for c in self._events.keys()]
            return reduce(lambda x, y: x + y, all_stats)
        else:
            return self._statistics[cpu][name]

    def get_histogram(self, cpu, name):
        if cpu == 'all':
            all_histos = [self._histograms[c][name] 
                          for c in self._events.keys()]
            return reduce(lambda x, y: x + y, all_histos)
        else:
            return self._histograms[cpu][name]

# --- Counting part ---

class Counts:
    def __init__(self, names):
        self._preset_names(names)
        self._preset_values(names)

    def _preset_names(self, names):
        self.edges = [names[0], names[-1]]
        self.names = names[1 : -1]

        self._edges = [n.replace(':', '__') for n in self.edges]
        self._names = [n.replace(':', '__') for n in self.names]

    def _preset_values(self, names):
        # Build a map to translate event names to indexes
        self._name_to_index = dict((n, i) for i, n in enumerate(self._names))

        self._record_status = False
        self._current_counts = None
        self._all_counts = []

    def update(self, event):
        if event.name == self._edges[0]:
            self._current_counts = [0 for _ in self.names]
            self._record_status = True
        elif self._record_status and event.name == self._edges[1]:
            self._all_counts.append(self._current_counts)
            self._current_counts = None
            self._record_status = False
        elif self._record_status and event.name in self._name_to_index:
            index = self._name_to_index[event.name]
            self._current_counts[index] += 1

    def getitems(self):
        names = self.names
        all_counts = self._all_counts
        self._all_counts = []

        all_counts = zip(*all_counts) if len(all_counts) > 0 else ([] * len(names))
        return dict([(n, all_counts[i]) for i, n in enumerate(names)])

# --- Counts analysis part ---

class Statistics:
    def __init__(self, stats = None):
        if stats is None:
            self.min = 1000000000
            self.max = 0
            self.sum = 0
            self.count = 0
        else:
            self.min = stats.min
            self.max = stats.max
            self.sum = stats.sum
            self.count = stats.count

    def __iadd__(self, other):
        if other.min < self.min:
            self.min = other.min
        if other.max > self.max:
            self.max = other.max
        self.sum += other.sum
        self.count += other.count
        return self

    def __add__(self, other):
        result = Statistics(stats = self)
        result += other
        return result

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
    def __init__(self, bucket_size = 10, buckets_count = 20, histo = None):
        if histo is None:
            self.step = bucket_size
            self.count = buckets_count
            self.buckets = [i for i in xrange(self.count)]
            self.histo = [0 for i in xrange(self.count)]
            self.overflow = 0
            self.total = 0
        else:
            self.step = histo.step
            self.count = histo.count
            self.buckets = histo.buckets
            self.histo = histo.histo[:]
            self.overflow = histo.overflow
            self.total = histo.total

    def __iadd__(self, other):
        for i, count in enumerate(other.histo):
            self.histo[i] += count
        self.overflow += other.overflow
        self.total += other.total
        return self

    def __add__(self, other):
        result = Histogram(histo = self)
        result += other
        return result

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

def print_legend(events):
    names = events.get_names()

    print '# === Legend ==='
    legends = ['# E{:02d}: {}'.format(i, n) for i, n in enumerate(names)]
    for legend in legends:
        print legend
    
def print_stats(events):
    names = events.get_names()
    cpus = events.get_cpus()

    print '# === Statistics: min avg max (ns) ==='
    tmp = ['{:^23}'.format(c) for c in cpus]
    print '# cpus: ' + ' | '.join(tmp)

    for i, name in enumerate(names):
        values = [events.get_statistics(c, name).get_values() for c in cpus]
        tmp = ['{:07d} {:07d} {:07d}'.format(v[0], v[2], v[1]) for v in values]
        line = '{:^6}: '.format('E{:02d}'.format(i)) + ' | '.join(tmp)
        print line

def print_histograms(events):
    names = events.get_names()
    cpus = events.get_cpus()
    bucket, count = events._config.histo

    print '# === Histograms: bucket:{} ==='.format(bucket)

    for i, name in enumerate(names):
        tmp = ['{:^4}'.format(c) for c in cpus]
        print ' E{:02d} \ cpus: '.format(i) + ' | '.join(tmp)

        histograms = [events.get_histogram(c, name) for c in cpus]
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

config = None
events = None

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
    events = Events(config)

def trace_end():
    events.flush()
    # Print the results (according to the configuration)
    print_legend(events)
    print_stats(events)
    if config.histo:
        print_histograms(events)

