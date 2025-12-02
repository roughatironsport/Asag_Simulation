#!/usr/bin/env python
"""
Simulation of train inspection via AI and human decision making

This simulation models a realistic train inspection process involving both AI-based pre-screening
and human inspector evaluation. It is designed using the SimPy discrete-event simulation framework
and includes the following key components:

1. **Human Inspectors**:
   - Organized into shift groups (`NUM_SHIFTS`) to stagger regular breaks and ensure continuous coverage.
   - Follow a structured work-rest cycle:
     - Regular breaks after a defined work period (e.g., 300 minutes), staggered by shift.
     - Occasional short breaks triggered randomly to simulate fatigue or interruptions.
   - Status is tracked using a `busy` flag and a shared resource pool.

2. **AI Inspection Layer**:
   - Trains may undergo an AI-based inspection before human evaluation.
   - The AI system can be configured with false positive and false negative rates to simulate imperfect detection.
   - AI results influence whether a train is forwarded to human inspection or cleared automatically.

3. **Train Handling and Damage Modeling**:
   - Trains arrive at random intervals and may carry randomly generated damage profiles.
   - Damage detection and classification are probabilistic, affecting inspection outcomes and resource usage.
   - Human and AI inspections interact with these profiles to determine the inspection path.

4. **Infrastructure Resources**:
   - Includes a limited number of `Abstellgleise` (sidings) as a SimPy resource.
   - Trains may need to wait for an available siding before inspection or repair.

5. **Temporal and Contextual Variables**:
   - The simulation tracks weekdays and can vary behavior based on the day (e.g., reduced staff on weekends).
   - Global variables control simulation parameters such as inspection durations, arrival rates, and break policies.

6. **Purpose and Use**:
   - This simulation is intended to evaluate the efficiency, reliability, and resilience of a hybrid inspection system.
   - It supports experimentation with different AI accuracy levels, staffing models, and infrastructure constraints.

The model is extensible and can be adapted for further complexity, such as repair workflows, cost tracking, or predictive maintenance strategies.
"""


import simpy
import random
import numpy as np
import numbers
import sys
import json
import os


__author__ = "Patric Schubert, Marius Lau, Lucija Heun, Christian Haas"
__copyright__ = "Copyright 2025, CoDive, https://codive.de/"
__credits__ = ["Patric Schubert", "Marius Lau", "Lucija Heun", "Christian Haas"]
__license__ = ""
__version__ = "1.2"
__maintainer__ = "Patric Schubert"
__email__ = "schubert@codive.de"
__status__ = "Prototype"

# Print stats
PRINT_STAT = False

# data setting from external json
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
JSON_PATH = os.path.join(PROJECT_DIR, "json_files", "simulation_data.json")

# DEFAULT PARAMETERS
# Simulation Parameters
SIM_TIME = 1440  # simulation time in minutes (a day: 1440)
WORKING_DAY = 1440  # actual working time in minutes (see: simulate_waiting_times)
WOCHENTAG = 'Dienstag'

# Station Parameters
ABSTELLGLEISE = 2  # integer
NUM_INSPECTORS = 3  # integer

# time to Abstellgleise
WALKING_DURATION = [500/180+5] * ABSTELLGLEISE
DRIVING_DURATION = [500/360+5] * ABSTELLGLEISE

# Inspector Parameters
HUMAN_DESC = True
    #    Time to inspect an axis
INSP_TIME_PER_AXES = 0.35  # mean: minutes; data source: PVG
SD_INSP_TIME_PER_AXES = 0.12  # sd: minutes; data source: PVG
    #    Time to inspect a wagon on screen
INSP_TIME_SCREEN_PER_WAGON = 1  # mean: minutes; data source: expert rating
SD_INSP_TIME_SCREEN_PER_WAGON = 0.2  # sd: minutes; data source: expert rating
    #    Time to inspect a damage in siding
INSP_CLOSER_LOOK = 2  # mean: minutes; data source: expert rating
SD_INSP_CLOSER_LOOK = 0.3  # sd: minutes; data source: expert rating
    #    Time to change an entry in PVG
TIME_PVG = 5  # mean: minutes
SD_TIME_PVG = 1  # sd: minutes
    #    Formality handling
FORMALITIES_BASELINE = 10  # minutes; time spent after train inspection
MEAN_NUM_FORMAL_ACTS = 0.2
MEAN_TIME_FORMALS = 10  # minutes
SD_TIME_FORMALS = 2  # minutes
    #    Probabilities
HUMAN_INSP_PROB = 0.99  # human probability of categorizing damages/nondamages
    #    Trust in AI parameter
TRUST_AI_PROB = 0.5  # Wahrscheinlichkeit in [0,1], dass der AI-Entscheidung geglaubt wird
    #    How to handle Inconsistencies
PROB_INCON_HANDLING = 0.5  # Wahrscheinlichkeit, dass Schaden vor Ort betrachtet werden muss
    #    Pausetimes
SHORT_PAUSE_MIN = 3
SHORT_PAUSE_MAX = 15
REGULAR_PAUSE = 30
NUM_SHIFTS = 3  # Anzahl der Schichtarbeiten

# Train Parameters
NUM_WAGONS = [10, 40]  # Integer interval of wagons per train
MEAN_NUM_DAMAGES = 0.05  # for poisson distribution: mean number of damages per wagon

# Parameter-Tabelle
PARAMS_WEEK = {
    "Montag": {"lambda1": 0.79789911, "lambda2": 0.20210089, "mu1": 57.18764, "mu2": 33.66652, "sigma1": 6.280481,
               "sigma2": 10.692359},
    "Dienstag": {"lambda1": 0.94000036, "lambda2": 0.05999964, "mu1": 59.04254, "mu2": 31.33332, "sigma1": 4.784562,
                 "sigma2": 2.054801},
    "Mittwoch": {"lambda1": 0.16511720, "lambda2": 0.83488280, "mu1": 32.21515, "mu2": 59.45929, "sigma1": 9.575718,
                 "sigma2": 5.695828},
    "Donnerstag": {"lambda1": 0.11963747, "lambda2": 0.88036253, "mu1": 29.35031, "mu2": 55.79886,
                   "sigma1": 3.431520, "sigma2": 6.858814},
    "Freitag": {"lambda1": 0.08048903, "lambda2": 0.91951097, "mu1": 22.51954, "mu2": 41.96937, "sigma1": 10.605621,
                "sigma2": 4.205904},
    "Samstag": {"lambda1": 0.93893170, "lambda2": 0.06106830, "mu1": 22.01913, "mu2": 22.99017, "sigma1": 3.080884,
                "sigma2": 18.694016},
    "Sonntag": {"lambda1": 0.30853715, "lambda2": 0.69146285, "mu1": 17.97782, "mu2": 25.60252, "sigma1": 2.225977,
                "sigma2": 3.230762}
}

NUM_POSSIBLE_AXES = 3  # number of axes that are possible
POSSIBLE_AXES = [4, 6, 8]  # Axes that are possible
PROBABILITIES_AXES = [0.6, 0.3, 0.1]  # Distribution of possible axes

# AI Parameters
AI_INSP = True
FALSE_NEGATIVE = 0.02
FALSE_POSITIVE = 0.01


def load_json_params():
    global SIM_TIME, \
        WORKING_DAY, \
        NUM_INSPECTORS, \
        INSP_TIME_PER_AXES, \
        SD_INSP_TIME_PER_AXES, \
        INSP_TIME_SCREEN_PER_WAGON, \
        SD_INSP_TIME_SCREEN_PER_WAGON, \
        INSP_CLOSER_LOOK, \
        SD_INSP_CLOSER_LOOK, \
        TIME_PVG, \
        SD_TIME_PVG, \
        FORMALITIES_BASELINE, \
        MEAN_NUM_FORMAL_ACTS, \
        MEAN_TIME_FORMALS, \
        SD_TIME_FORMALS, \
        HUMAN_INSP_PROB, \
        TRUST_AI_PROB, \
        PROB_INCON_HANDLING, \
        SHORT_PAUSE_MIN, \
        SHORT_PAUSE_MAX, \
        REGULAR_PAUSE, \
        NUM_SHIFTS, \
        FALSE_NEGATIVE, \
        FALSE_POSITIVE, \
        ABSTELLGLEISE, \
        WALKING_DURATION, \
        DRIVING_DURATION
    if os.path.isfile(JSON_PATH):
        try:
            with open(JSON_PATH, 'r') as f:
                data = json.load(f)
                SIM_TIME = data.get("SIM_TIME", SIM_TIME)
                WORKING_DAY = data.get("WORKING_DAY", WORKING_DAY)
                NUM_INSPECTORS = data.get("NUM_INSPECTORS", NUM_INSPECTORS)
                INSP_TIME_PER_AXES = data.get("INSP_TIME_PER_AXES", INSP_TIME_PER_AXES)
                SD_INSP_TIME_PER_AXES = data.get("SD_INSP_TIME_PER_AXES", SD_INSP_TIME_PER_AXES)
                INSP_TIME_SCREEN_PER_WAGON = data.get("INSP_TIME_SCREEN_PER_WAGON", INSP_TIME_SCREEN_PER_WAGON)
                SD_INSP_TIME_SCREEN_PER_WAGON = data.get("SD_INSP_TIME_SCREEN_PER_WAGON", SD_INSP_TIME_SCREEN_PER_WAGON)
                INSP_CLOSER_LOOK = data.get("INSP_CLOSER_LOOK", INSP_CLOSER_LOOK)
                SD_INSP_CLOSER_LOOK = data.get("SD_INSP_CLOSER_LOOK", SD_INSP_CLOSER_LOOK)
                TIME_PVG = data.get("TIME_PVG", TIME_PVG)
                SD_TIME_PVG = data.get("SD_TIME_PVG", SD_TIME_PVG)
                FORMALITIES_BASELINE = data.get("FORMALITIES_BASELINE", FORMALITIES_BASELINE)
                MEAN_NUM_FORMAL_ACTS = data.get("MEAN_NUM_FORMAL_ACTS", MEAN_NUM_FORMAL_ACTS)
                MEAN_TIME_FORMALS = data.get("MEAN_TIME_FORMALS", MEAN_TIME_FORMALS)
                SD_TIME_FORMALS = data.get("SD_TIME_FORMALS", SD_TIME_FORMALS)
                HUMAN_INSP_PROB = data.get("HUMAN_INSP_PROB", HUMAN_INSP_PROB)
                TRUST_AI_PROB = data.get("TRUST_AI_PROB", TRUST_AI_PROB)
                PROB_INCON_HANDLING = data.get("PROB_INCON_HANDLING", PROB_INCON_HANDLING)
                SHORT_PAUSE_MIN = data.get("SHORT_PAUSE_MIN", SHORT_PAUSE_MIN)
                SHORT_PAUSE_MAX = data.get("SHORT_PAUSE_MAX", SHORT_PAUSE_MAX)
                REGULAR_PAUSE = data.get("REGULAR_PAUSE", REGULAR_PAUSE)
                NUM_SHIFTS = data.get("NUM_SHIFTS", NUM_SHIFTS)
                FALSE_NEGATIVE = data.get("FALSE_NEGATIVE", FALSE_NEGATIVE)
                FALSE_POSITIVE = data.get("FALSE_POSITIVE", FALSE_POSITIVE)

                # ABSTELLGLEISE aus simulation_distances.gleise
                if "simulation_distances" in data and "gleise" in data["simulation_distances"]:
                    ABSTELLGLEISE = len(data["simulation_distances"]["gleise"])
                    WALKING_DURATION = [z / 180 + 5 for z in data["simulation_distances"]["zentrale"]]
                    DRIVING_DURATION = [g / 360 + 5 for g in data["simulation_distances"]["gleise"]]
        except Exception as e:
            print(f"Fehler beim Laden der JSON-Datei: {e}")
    else:
        print(f"Keine JSON-Datei gefunden unter: {JSON_PATH}")


def validiere_eingaben():

    # Hilfsfunktionen
    def ist_positive_zahl(x): return isinstance(x, numbers.Number) and x > 0
    def ist_positive_int(x): return isinstance(x, int) and x > 0
    def ist_nichtnegative_int(x): return isinstance(x, int) and x >= 0
    def ist_bool(x): return isinstance(x, bool)
    def ist_wahrscheinlichkeit(x): return isinstance(x, float) and 0 < x < 1

    # Einfache numerische Prüfungen
    assert ist_positive_int(SIM_TIME), "SIM_TIME muss eine positive ganze Zahl sein"
    assert ist_positive_int(WORKING_DAY), "WORKING_DAY muss eine positive ganze Zahl sein"
    assert ist_positive_int(ABSTELLGLEISE), "ABSTELLGLEISE muss eine positive ganze Zahl sein"
    assert ist_positive_int(NUM_INSPECTORS), "NUM_INSPECTORS muss eine positive ganze Zahl sein"
    assert ist_bool(HUMAN_DESC), "HUMAN_DESC muss ein boolescher Wert sein"
    assert ist_positive_zahl(INSP_TIME_PER_AXES), "INSP_TIME_PER_AXES muss positiv sein"
    assert ist_positive_zahl(SD_INSP_TIME_PER_AXES), "SD_INSP_TIME_PER_AXES muss positiv sein"
    assert ist_positive_zahl(INSP_TIME_SCREEN_PER_WAGON), "INSP_TIME_SCREEN_PER_WAGON muss positiv sein"
    assert ist_positive_zahl(SD_INSP_TIME_SCREEN_PER_WAGON), "SD_INSP_TIME_SCREEN_PER_WAGON muss positiv sein"
    assert ist_positive_zahl(INSP_CLOSER_LOOK), "INSP_CLOSER_LOOK muss positiv sein"
    assert ist_positive_zahl(SD_INSP_CLOSER_LOOK), "SD_INSP_CLOSER_LOOK muss positiv sein"
    assert ist_positive_zahl(TIME_PVG), "TIME_PVG muss positiv sein"
    assert ist_positive_zahl(SD_TIME_PVG), "SD_TIME_PVG muss positiv sein"
    assert ist_positive_zahl(FORMALITIES_BASELINE), "FORMALITIES_BASELINE muss positiv sein"
    assert ist_positive_zahl(MEAN_NUM_FORMAL_ACTS), "MEAN_NUM_FORMAL_ACTS muss eine Zahl größer oder gleich 0 sein"
    assert ist_positive_zahl(MEAN_TIME_FORMALS), "MEAN_TIME_FORMALS muss positiv sein"
    assert ist_positive_zahl(SD_TIME_FORMALS), "SD_TIME_FORMALS muss positiv sein"
    assert ist_wahrscheinlichkeit(HUMAN_INSP_PROB), "HUMAN_INSP_PROB muss zwischen 0 und 1 liegen"
    assert ist_wahrscheinlichkeit(TRUST_AI_PROB), "TRUST_AI_PROB muss zwischen 0 und 1 liegen"
    assert ist_wahrscheinlichkeit(PROB_INCON_HANDLING), "PROB_INCON_HANDLING muss zwischen 0 und 1 liegen"
    assert ist_positive_int(SHORT_PAUSE_MIN), "SHORT_PAUSE_MIN muss eine positive ganze Zahl sein"
    assert ist_positive_int(SHORT_PAUSE_MAX), "SHORT_PAUSE_MAX muss eine positive ganze Zahl sein"
    assert ist_positive_int(REGULAR_PAUSE), "REGULAR_PAUSE muss eine positive ganze Zahl sein"
    assert ist_positive_int(NUM_SHIFTS), "NUM_SHIFTS muss eine positive ganze Zahl sein"
    assert ist_positive_zahl(MEAN_NUM_DAMAGES), "MEAN_NUM_DAMAGES muss positiv sein"
    assert ist_bool(AI_INSP), "AI_INSP muss ein boolescher Wert sein"
    assert ist_wahrscheinlichkeit(FALSE_NEGATIVE), "FALSE_NEGATIVE muss zwischen 0 und 1 liegen"
    assert ist_wahrscheinlichkeit(FALSE_POSITIVE), "FALSE_POSITIVE muss zwischen 0 und 1 liegen"
    assert ist_positive_int(NUM_POSSIBLE_AXES), "NUM_POSSIBLE_AXES muss eine positive ganze Zahl sein"

    # Listen- und Intervallprüfungen
    assert isinstance(NUM_WAGONS, list) and len(NUM_WAGONS) == 2 and all(ist_positive_int(x) for x in NUM_WAGONS), "NUM_WAGONS muss eine Liste aus zwei positiven ganzen Zahlen sein"
    assert isinstance(POSSIBLE_AXES, list) and len(POSSIBLE_AXES) == NUM_POSSIBLE_AXES and all(ist_positive_int(x) for x in POSSIBLE_AXES), f"POSSIBLE_AXES muss eine Liste aus {NUM_POSSIBLE_AXES} positiven ganzen Zahlen sein"
    assert isinstance(PROBABILITIES_AXES, list) and len(PROBABILITIES_AXES) == NUM_POSSIBLE_AXES and all(ist_wahrscheinlichkeit(x) for x in PROBABILITIES_AXES), f"PROBABILITIES_AXES muss eine Liste aus {NUM_POSSIBLE_AXES} Wahrscheinlichkeiten sein"
    assert abs(sum(PROBABILITIES_AXES) - 1.0) < 1e-6, "Die Summe der PROBABILITIES_AXES muss 1 ergeben"

    # Wochentag und PARAMS_WEEK
    assert isinstance(WOCHENTAG, str), "WOCHENTAG muss ein String sein"
    assert WOCHENTAG in PARAMS_WEEK, f"WOCHENTAG '{WOCHENTAG}' ist ungültig. Muss einer der Schlüssel in PARAMS_WEEK sein"
    for tag, werte in PARAMS_WEEK.items():
        for key in ["lambda1", "lambda2", "mu1", "mu2", "sigma1", "sigma2"]:
            assert key in werte and ist_positive_zahl(werte[key]), f"{key} in PARAMS_WEEK[{tag}] muss positiv sein"

    if PRINT_STAT:
        print("✅ Alle globalen Variableneingaben sind gültig.")


class InspectorPool:
    def __init__(self, env, num_inspectors):
        self.env = env
        self.available_inspectors = simpy.Store(env)
        self.inspectors = [Inspector(env, i, self.available_inspectors) for i in range(num_inspectors)]

    def print_statistics(self):
        print("\n--- Statistik: Anzahl begutachteter Züge und Pausenzeiten pro Wagenmeister ---")
        for inspector in self.inspectors:
            print(f"Wagenmeister {inspector.id}:")
            print(f"  - Züge begutachtet         : {inspector.inspected_trains}")
            print(f"  - Begutachtungszeit (total): {round(inspector.total_inspection_time,1)} Minuten")
            print(f"     - davon im Gleis        : {round(inspector.time_in_siding,1)} Minuten")
            print(f"  - Gesamte Pausenzeit       : {inspector.total_pause_time} Minuten")
            print(f"__________________________________")


class Inspector:
    def __init__(self, env, inspector_id, available_store):
        self.env = env
        self.id = inspector_id
        self.resource = simpy.Resource(env, capacity=1)
        self.available_store = available_store
        self.busy = False
        self.shift_group = inspector_id % NUM_SHIFTS  # Schichtgruppe 0 oder 1
        self.inspected_trains = 0
        self.total_inspection_time = 0
        self.total_pause_time = 0
        self.num_in_siding = 0
        self.time_in_siding = 0
        env.process(self.pause_manager())
        env.process(self.make_available())

    def make_available(self):
        yield self.available_store.put(self)

    @staticmethod
    def working_time(num, mean_time, sd_time):
        """Calculates inspection time as a normal distributed random variable

        The formula is due to the fact that the sum of n random variables
        with X~N(m,s) is equivalent to Y~N(nm,sqrt(n)*m)
        """

        t = 0
        if num > 0:
            m = num
            s = np.sqrt(m)
            t = random.normalvariate(m * mean_time, s * sd_time)
            while t <= 0:
                t = random.normalvariate(m * mean_time, s * sd_time)
        return t


    @staticmethod
    def model_human_inspection(num_damages, num_fp, dam_found_AI):
        """Modelling human inspection"""

        if AI_INSP:
            dam_bestaetigt = np.random.binomial(dam_found_AI, HUMAN_INSP_PROB)
            total_human_fn_umklassifiziert = np.random.binomial(num_damages-dam_found_AI, HUMAN_INSP_PROB *
                                                                (1 - TRUST_AI_PROB))
            total_human_damages = dam_bestaetigt + total_human_fn_umklassifiziert
            total_human_fp_umklassifiziert = np.random.binomial(num_fp, HUMAN_INSP_PROB *
                                                                (1 - TRUST_AI_PROB))
        else:
            total_human_damages = np.random.binomial(num_damages, HUMAN_INSP_PROB)
            total_human_fp_umklassifiziert = 0
            total_human_fn_umklassifiziert = 0
        return total_human_damages, total_human_fp_umklassifiziert, total_human_fn_umklassifiziert

    @staticmethod
    def formalities(num):
        formalities = np.random.poisson(lam=MEAN_NUM_FORMAL_ACTS, size=num)
        total_formalities = np.sum(formalities)
        return total_formalities

    def pause_manager(self):
        work_time_counter = 0
        while True:
            interval = 10
            yield self.env.timeout(interval)
            work_time_counter += interval

            # Kurze Pause mit geringer Wahrscheinlichkeit
            if random.random() < 0.05 and not self.busy and self in self.available_store.items:
                self.available_store.items.remove(self)
                self.busy = True
                SHORT_PAUSE = [SHORT_PAUSE_MIN, SHORT_PAUSE_MAX]
                pause_duration = random.randint(*SHORT_PAUSE)
                self.total_pause_time += pause_duration
                if PRINT_STAT:
                    print(
                        f'>>>    Zeit: {self.env.now} ### Wagenmeister {self.id} macht eine kurze Pause ({pause_duration} Minuten)')
                yield self.env.timeout(pause_duration)
                if PRINT_STAT:
                    print(f'>>>    Zeit: {self.env.now} ### Wagenmeister {self.id} ist zurück aus der kurzen Pause')
                self.busy = False
                yield self.available_store.put(self)

            # Reguläre Pause nach Schichtplan
            pause_threshold = 300 + self.shift_group * 60  # z.B. Schicht 0 → 300, Schicht 1 → 360, ...
            if work_time_counter >= pause_threshold and not self.busy and self in self.available_store.items:
                self.available_store.items.remove(self)
                self.busy = True
                pause_duration = 30
                self.total_pause_time += pause_duration
                if PRINT_STAT:
                    print(f'>>>    Zeit: {self.env.now} ### Wagenmeister {self.id} (Schicht {self.shift_group}) '
                          f'macht reguläre Pause ({pause_duration} Minuten)')
                yield self.env.timeout(pause_duration)
                if PRINT_STAT:
                    print(f'>>>    Zeit: {self.env.now} ### Wagenmeister {self.id} ist zurück aus der regulären Pause')
                self.busy = False
                yield self.available_store.put(self)
                work_time_counter = 0


class InspectorAI:
    def __init__(self, env, fp_rate, fn_rate):
        self.fp = fp_rate
        self.fn = fn_rate

    def model_false_positives(self, num_wagons):
        """Function which gives a number of false positives due to Poisson distribution"""

        # number of wrong damages found by AI modelled via Poisson-distribution
        fp_per_wagon = np.random.poisson(lam=self.fp, size=num_wagons)

        # Sum the false positives to get the total number for the train
        total_fp = np.sum(fp_per_wagon)
        return total_fp

    def model_false_negatives(self, num_damages):
        """Function which gives a number of false negatives due to Binomial distribution"""

        # real damages that were not found by AI modelled via binomial distribution (from number of true damages)
        total_fn = np.random.binomial(num_damages, self.fn)
        return total_fn


class Train:
    def __init__(self, env, zug_nummer, abstellgleise, gleis_nummer, inspector_pool, ai_system, train_stats):
        """Generates a train object

        env: simpy environment
        zug_nummer: int
        abstellgleise: simpy ressource
        gleis_nummer: int
        inspectors: simpy ressource
        inspector_nummer: int
        """

        self.env = env
        self.departure = 0
        self.arrival_time = 0
        self.train_stats = train_stats

        self.zug_nummer = zug_nummer
        self.gleis_nummer = gleis_nummer

        self.num_wagons = random.randint(*NUM_WAGONS)
        self.num_axes = self.calculate_total_axes(self.num_wagons)
        self.num_damages = self.model_damages_for_train(self.num_wagons)  # IST-Schäden

        self.waiting_time = 0
        self.stay_time = 0

        self.ai_system = ai_system

        self.inspector_pool = inspector_pool
        env.process(self.twb(abstellgleise))

    def calculate_total_axes(self, num_wagons):
        """Function which calculates number of total axes by use of a probability distribution"""

        # Definiere die Achsen und ihre Wahrscheinlichkeiten
        axles = POSSIBLE_AXES
        prob = PROBABILITIES_AXES

        # Generiere zufällig Achsen für jeden Wagon basierend auf den Wahrscheinlichkeiten
        total_axles = sum(random.choices(axles, prob, k=num_wagons))
        return total_axles

    def model_damages_for_train(self, num_wagons):
        """Function which models number of damages due to Poisson distribution"""

        # Generate Poisson-distributed random variables for each wagon
        damages_per_wagon = np.random.poisson(lam=MEAN_NUM_DAMAGES, size=num_wagons)

        # Sum the damages to get the total number of damages for the train
        total_damages = np.sum(damages_per_wagon)
        return total_damages

    def twb(self, abstellgleise):
        """technische Wagenbehandlung"""

        waiting_begin = None
        if abstellgleise[self.gleis_nummer].count >= abstellgleise[self.gleis_nummer].capacity:
            if PRINT_STAT:
                print(f'Zeit: {self.env.now} ### Zug {self.zug_nummer} wartet vor Abstellgleis {self.gleis_nummer + 1} '
                      f'mit {self.num_wagons} Wagen')
            waiting_begin = self.env.now

        with abstellgleise[self.gleis_nummer].request() as req_abst:
            yield req_abst

            #fahrtzeit in abh. infrastruktur
            fahrzeit = DRIVING_DURATION[self.gleis_nummer]
            if PRINT_STAT:
                print(f'Zeit: {self.env.now} ### Zug {self.zug_nummer} fährt auf Abstellgleis {self.gleis_nummer + 1} und benötigt {fahrzeit}')
            yield self.env.timeout(fahrzeit)

            self.arrival_time = self.env.now

            if waiting_begin is not None:
                self.waiting_time = self.arrival_time - waiting_begin

            dam_found_AI, fn, fp = 0, 0, 0
            if AI_INSP:
                fn = self.ai_system.model_false_negatives(self.num_damages)
                fp = self.ai_system.model_false_positives(self.num_wagons)
                dam_found_AI = self.num_damages - fn
                if PRINT_STAT:
                    print(f'---### Der Zug hat {self.num_damages} Schaeden.')
                    print(f'---### AI: Gefundene Schaeden: {dam_found_AI+fp}. Hiervon sind {fp} false positives (zusätzlich '
                          f'gefundene Schäden, welche keine sind). Es existieren {fn} false negatives (nicht gefundene '
                          f'wahre Schäden).')

            # request inspector if human decision
            if HUMAN_DESC:

                inspector = yield self.inspector_pool.available_inspectors.get()
                inspector.busy = True
                with inspector.resource.request() as req_insp:
                    yield req_insp

                    if PRINT_STAT:
                        print(f'Zeit: {self.env.now} ### Wagenmeister {inspector.id} begutachtet digital '
                              f'Zug {self.zug_nummer}')

                    begutachtungszeit_screen = inspector.working_time(self.num_wagons, INSP_TIME_SCREEN_PER_WAGON,
                                                                      SD_INSP_TIME_SCREEN_PER_WAGON)
                    yield self.env.timeout(begutachtungszeit_screen)

                    total_human_damages, total_human_fp_umklassifiziert, total_human_fn_umklassifiziert = \
                        inspector.model_human_inspection(self.num_damages, fp, dam_found_AI)

                    num_umklassifiziert = total_human_fp_umklassifiziert + total_human_fn_umklassifiziert
                    umklasszeit = 0
                    if num_umklassifiziert > 0:
                        umklasszeit = inspector.working_time(num_umklassifiziert, TIME_PVG, SD_TIME_PVG)
                        yield self.env.timeout(umklasszeit)

                    num_inconsistencies = total_human_damages - dam_found_AI + num_umklassifiziert
                    additional_time, wegezeit, begutachtungszeit_gleis, additional_PVG_change_time = 0, 0, 0, 0
                    if num_inconsistencies > 0:
                        num = np.random.binomial(num_inconsistencies, PROB_INCON_HANDLING)
                        if num > 0:
                            # wegezeit in abh. von infrastruktur
                            wegezeit = WALKING_DURATION[self.gleis_nummer]
                            if PRINT_STAT:
                                print(f'    Zeit: {self.env.now} ### Zug {self.zug_nummer}: Wagenmeister '
                                      f'{inspector.id} muss wegen {num} Inkonsistenzen in das Gleis und braucht {wegezeit}.')
                            yield self.env.timeout(wegezeit)

                            begutachtungszeit_gleis = inspector.working_time(num, INSP_CLOSER_LOOK, SD_INSP_CLOSER_LOOK)
                            yield self.env.timeout(begutachtungszeit_gleis)
                            num_PVG_change = np.random.binomial(num, HUMAN_INSP_PROB)
                            additional_PVG_change_time = 0
                            if num_PVG_change > 0:
                                additional_PVG_change_time = inspector.working_time(num_PVG_change, TIME_PVG, SD_TIME_PVG)
                                yield self.env.timeout(additional_PVG_change_time)
                            if PRINT_STAT:
                                print(f'    Zeit: {self.env.now} ### Zug {self.zug_nummer}: Wagenmeister '
                                      f'{inspector.id} hat {num} Inkonsistenzen im Gleis begutachtet und '
                                      f'{num_PVG_change} im PVG geändert. Rückweg benötigt {wegezeit}.')
                            yield self.env.timeout(wegezeit)
                            inspector.num_in_siding += 1
                            additional_time = 2*wegezeit + begutachtungszeit_gleis + additional_PVG_change_time
                            inspector.time_in_siding += additional_time

                    hum_found_damages = total_human_damages + total_human_fn_umklassifiziert
                    num_formals = inspector.formalities(hum_found_damages)
                    formality_time = FORMALITIES_BASELINE
                    if num_formals > 0:
                        formality_time += inspector.working_time(num_formals, MEAN_TIME_FORMALS, SD_TIME_FORMALS)
                        yield self.env.timeout(formality_time)

                    inspector.inspected_trains += 1
                    inspector.total_inspection_time += begutachtungszeit_screen + additional_time

                    if PRINT_STAT:
                        print(f'____________________________________________________________________________')
                        print(f'Zeit: {self.env.now} ### Wagenmeister {inspector.id} hat Zug {self.zug_nummer} '
                              f'fertig begutachtet')
                        print(f'Zeit: {self.env.now} ### Ergebnis von Zug {self.zug_nummer}:')
                        print(f'---### Wagenmeister {inspector.id} hat {total_human_damages} von '
                              f'{self.num_damages} wahren Schäden gefunden. AI hat {dam_found_AI + fp} gefunden.')
                        print(f'---### Wagenmeister {inspector.id} hat {total_human_fp_umklassifiziert} '
                              f'von {fp} false positives, und {total_human_fn_umklassifiziert} false negatives '
                              f'umklassifiziert.')
                        print(f'          Begutachtungszeit (digital)    : {round(begutachtungszeit_screen, 1)}')
                        print(f'          PVG-Änderungen (digital)       : {round(umklasszeit, 1)}')
                        print(f'          Formalitäten/Akten             : {round(formality_time, 1)}')
                        print(f'          Wegezeit (Gleis)               : {round(wegezeit*2, 1)}')
                        print(f'          Begutachtungszeit (Gleis)      : {round(begutachtungszeit_gleis, 1)}')
                        print(f'          PVG-Änderungen (Gleis)         : {round(additional_PVG_change_time, 1)}')
                        print(f'____________________________________________________________________________')

                    yield self.inspector_pool.available_inspectors.put(inspector)
                    inspector.busy = False

            self.departure = self.env.now
            self.stay_time = self.departure - self.arrival_time
            if PRINT_STAT:
                print(f'Zeit: {self.env.now} ### Zug {self.zug_nummer} verlässt Abstellgleis {self.gleis_nummer + 1}')
                print(f'       Wartezeit: {self.waiting_time}')
                print(f'       Standzeit: {round(self.stay_time,1)}')

        # Dictionary für diesen Zug
        zug_dict = {
            "zug_id": int(self.zug_nummer),
            "arrival": float(self.arrival_time),
            "departure": float(self.departure),
            "stay_time": float(self.stay_time),
            "Fahrzeit": float(fahrzeit),
            "Wartezeit": float(self.waiting_time),
            "true_damages": int(self.num_damages),
            "ai_found": int(dam_found_AI),
            "ai_fp": int(fp),
            "ai_fn": int(fn),
            "human_found": int(total_human_damages),
            "human_fp_umklassifiziert": int(total_human_fp_umklassifiziert),
            "human_fn_umklassifiziert": int(total_human_fn_umklassifiziert)
        }

        # Globale Liste füllen
        self.train_stats.append(zug_dict)

def simulate_waiting_times(weekday, n, total_time=WORKING_DAY):
    """Computes random numbers for waiting times between trains based on mixed normal distribution"""

    param = PARAMS_WEEK[weekday]
    # Simuliere X1 und X2
    X1 = np.random.normal(param["mu1"], param["sigma1"], n)
    X2 = np.random.normal(param["mu2"], param["sigma2"], n)
    # Berechne gewichtete Mischung
    X = param["lambda1"] * X1 + param["lambda2"] * X2
    # Berechne Wartezeiten
    W = total_time / X
    return float(W[0])


def zug_generator(env, abstellgleise, inspector_pool, ai_system, train_stats):
    """Generating train classes"""

    zug_nummer = 0
    while True:
        yield env.timeout(simulate_waiting_times(WOCHENTAG, n=1))
        zug_nummer += 1
        gleis_nummer = zug_nummer % len(abstellgleise)
        Train(env, zug_nummer, abstellgleise, gleis_nummer, inspector_pool, ai_system, train_stats)


def run_simulation_once(step_id=0):
    """Einzelne Simulation mit optionaler Schritt-ID"""

    try:
        validiere_eingaben()
    except AssertionError as e:
        print("❌ Falsche Eingabe:", e)
        return

    if PRINT_STAT:
        print(f'Simulation {step_id} start: {WOCHENTAG}')

    env = simpy.Environment()

    # Ressourcen und Klassen
    abstellgleise = [simpy.Resource(env) for _ in range(ABSTELLGLEISE)]
    inspector_pool = InspectorPool(env, NUM_INSPECTORS)
    ai_system = InspectorAI(env, FALSE_POSITIVE, FALSE_NEGATIVE)

    # Liste für Zugstatistiken
    train_results = []

    # Starte die Zugankunft
    env.process(zug_generator(env, abstellgleise, inspector_pool, ai_system, train_results))

    # Simulation für eine bestimmte Zeit laufen lassen
    env.run(until=SIM_TIME)
    if PRINT_STAT:
        print(f'Simulation {step_id} end with simulation time: {SIM_TIME}')
        inspector_pool.print_statistics()

        print("\n_____________________________________________________\n")

        for res in train_results:
            print(res)

    # Ergebnisse sammeln
    inspector_results = [
        {
            "id": inspector.id,
            "inspected_trains": inspector.inspected_trains,
            "total_inspection_time": inspector.total_inspection_time,
            "time_in_siding": inspector.time_in_siding,
            "total_pause_time": inspector.total_pause_time
        }
        for inspector in inspector_pool.inspectors
    ]

    # Kombiniertes Ergebnis
    combined_results = {
        "inspectors": inspector_results,
        "trains": train_results
    }

    # Speichern als JSON
    with open(f"results_step_{step_id}.json", "w") as f:
        json.dump(combined_results, f)


if __name__ == "__main__":
    step_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    load_json_params()
    run_simulation_once(step_id)
