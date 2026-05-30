from psychopy import visual, core, event, gui
import serial
from pathlib import Path
import random
import csv

# ======================================
# INDSTILLINGER
# ======================================
Base_folder = Path(__file__).parent
image_folder = Base_folder / "stimuli"
results_folder = Base_folder / "results"
results_folder.mkdir(exist_ok=True)

n_blocks = 6
n_targets = 6
n_test_trials = 30
n_old_trials = 15
n_new_trials = 15

study_face_duration = 15.0
fixation_duration = 0.5
iti_duration = 0.3

yes_key = "left"
no_key = "right"
quit_key = "escape"

valid_extensions = {".jpg", ".jpeg", ".png"}

# ======================================
# DATAKLARGØRING
# ======================================
results = []
participant = "test"
win = None


# ======================================
# HJÆLPEFUNKTIONER
# ======================================
USE_EEG = True  # slå til når du har hardware

if USE_EEG:
    port = serial.Serial("COM3", 115200)
else:
    port = None
    

#port = serial.Serial("COM4", 115200)  # address for serial port is COM4 in this example. Change to match your machine.

TRIGGERS = {
    "study_onset": 10,
    "test_old_onset": 20,
    "test_new_onset": 21,
    "response_yes": 30,
    "response_no": 31,
    "confidence_start": 40,
    "confidence_confirm": 41,
    "block_start": 50,
    "block_end": 51,
}

def trigger(code):
    if port is not None:
        port.write(code.to_bytes(1, "big"))
    print(f"trigger sent {code}")


def parse_identity_and_angle(file_path):
    """
    Finder identitet og vinkel fra filnavn.
    Fx:
        ABC01S.jpg  -> identity=ABC01, angle=S
        ABC01HL.jpg -> identity=ABC01, angle=HL
        ABC01FL.jpg -> identity=ABC01, angle=FL
    """
    stem = file_path.stem.upper()

    if stem.endswith("HL"):
        return stem[:-2], "HL"
    elif stem.endswith("FL"):
        return stem[:-2], "FL"
    elif stem.endswith("S"):
        return stem[:-1], "S"
    else:
        return None, None


def save_results():
    global results, participant, results_folder

    if len(results) == 0:
        return

    output_file = results_folder / f"{participant}_face_memory_results.csv"

    fieldnames = [
        "participant",
        "block_num",
        "block_gender",
        "trial_num",
        "identity",
        "angle",
        "status",
        "correct_answer",
        "response",
        "correct",
        "confidence",
        "response_rt",
        "rating_rt",
        "file_name"
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def quit_experiment():
    global win, port
    save_results()
    if port.is_open:
        port.close()
    if win is not None:
        win.close()
    core.quit()


def check_quit(keys):
    if keys is None:
        return
    key_names = [k[0] if isinstance(k, tuple) else k for k in keys]
    if quit_key in key_names:
        quit_experiment()


def safe_wait(duration):
    timer = core.Clock()
    while timer.getTime() < duration:
        keys = event.getKeys(keyList=[quit_key])
        if quit_key in keys:
            quit_experiment()
        core.wait(0.01)


def show_message(win, text, key_list=None):
    msg = visual.TextStim(
        win,
        text=text,
        color="white",
        height=0.05,
        wrapWidth=1.4
    )
    msg.draw()
    win.flip()

    if key_list is None:
        keys = event.waitKeys()
        check_quit(keys)
    else:
        keys = event.waitKeys(keyList=key_list)
        check_quit(keys)

def balanced_angle_sample(candidates, n_total=15):
    """
    Forsøger at vælge ca. lige mange S, HL, FL.
    Standard ved 15 trials = 5 af hver.
    """
    by_angle = {"S": [], "HL": [], "FL": []}

    for item in candidates:
        by_angle[item["angle"]].append(item)

    for angle in by_angle:
        random.shuffle(by_angle[angle])

    target_each = n_total // 3   # 5 hvis 15
    chosen = []

    # tag først 5 af hver hvis muligt
    for angle in ["S", "HL", "FL"]:
        take = min(target_each, len(by_angle[angle]))
        chosen.extend(by_angle[angle][:take])
        by_angle[angle] = by_angle[angle][take:]

    # mangler vi nogle, fyld op fra resten
    remaining = []
    for angle in ["S", "HL", "FL"]:
        remaining.extend(by_angle[angle])

    random.shuffle(remaining)

    while len(chosen) < n_total and remaining:
        chosen.append(remaining.pop())

    return chosen


# ======================================
# INDLÆS BILLEDER
# ======================================
all_files = [
    p for p in image_folder.iterdir()
    if p.is_file() and p.suffix.lower() in valid_extensions
]

identity_dict = {}
# struktur:
# identity_dict["ABC01"] = {"S": Path(...), "HL": Path(...), "FL": Path(...)}

for file_path in all_files:
    identity, angle = parse_identity_and_angle(file_path)
    if identity is None:
        continue

    if identity not in identity_dict:
        identity_dict[identity] = {}

    identity_dict[identity][angle] = file_path

# behold kun identiteter med alle tre vinkler
identity_dict = {
    ident: angles
    for ident, angles in identity_dict.items()
    if {"S", "HL", "FL"}.issubset(angles.keys())
}

all_identities = list(identity_dict.keys())

if len(all_identities) == 0:
    raise ValueError("Ingen gyldige billeder fundet i stimuli-mappen.")


# ======================================
# DELTAGERINFO
# ======================================
info = {"participant": ""}
dlg = gui.DlgFromDict(info, title="Face Memory Task")
if not dlg.OK:
    core.quit()

participant = info["participant"].strip()
if participant == "":
    participant = "test"


# ======================================
# FORDEL IDENTITETER EFTER KØN
# ======================================
random.shuffle(all_identities)

women_identities = []
men_identities = []

for ident in all_identities:
    if ident.startswith("AF"):
        women_identities.append(ident)
    elif ident.startswith("AM"):
        men_identities.append(ident)

blocks_per_gender = n_blocks // 2
needed_targets_per_gender = blocks_per_gender * n_targets  # 18

if len(women_identities) < needed_targets_per_gender:
    raise ValueError(
        f"Der er kun {len(women_identities)} kvinde-identiteter, "
        f"men der kræves mindst {needed_targets_per_gender}."
    )

if len(men_identities) < needed_targets_per_gender:
    raise ValueError(
        f"Der er kun {len(men_identities)} mande-identiteter, "
        f"men der kræves mindst {needed_targets_per_gender}."
    )

# ======================================
# GLOBAL PLANLÆGNING
# targets må aldrig senere være distractors
# ======================================
random.shuffle(women_identities)
random.shuffle(men_identities)

women_target_all = women_identities[:needed_targets_per_gender]
men_target_all = men_identities[:needed_targets_per_gender]

women_distractor_all = women_identities[needed_targets_per_gender:]
men_distractor_all = men_identities[needed_targets_per_gender:]

women_target_blocks = [
    women_target_all[i:i+n_targets]
    for i in range(0, len(women_target_all), n_targets)
]

men_target_blocks = [
    men_target_all[i:i+n_targets]
    for i in range(0, len(men_target_all), n_targets)
]

if len(women_target_blocks) != blocks_per_gender:
    raise ValueError("Fejl i planlægning af kvinde-targetblokke.")

if len(men_target_blocks) != blocks_per_gender:
    raise ValueError("Fejl i planlægning af mande-targetblokke.")

# distractor-puljer består KUN af identiteter, som aldrig er targets
available_women_distractor_images = []
available_men_distractor_images = []

for ident in women_distractor_all:
    for angle in ["S", "HL", "FL"]:
        available_women_distractor_images.append({
            "identity": ident,
            "angle": angle,
            "file": identity_dict[ident][angle]
        })

for ident in men_distractor_all:
    for angle in ["S", "HL", "FL"]:
        available_men_distractor_images.append({
            "identity": ident,
            "angle": angle,
            "file": identity_dict[ident][angle]
        })

# kvinder: 16 identiteter tilbage -> 16*3 = 48 distractorbilleder
if len(available_women_distractor_images) < (blocks_per_gender * n_new_trials):
    raise ValueError(
        "Der er ikke nok kvinde-distractorbilleder til dette design."
    )

# mænd: 12 identiteter tilbage -> 12*3 = 36 distractorbilleder
# men der skal bruges 45 distractor-trials, så 9 skal genbruges senere
if len(available_men_distractor_images) < 36:
    raise ValueError(
        "Der er ikke nok mande-distractorbilleder til den planlagte løsning."
    )

women_block_index = 0
men_block_index = 0

# gem distractors fra første mande-blok
male_block1_distractors = []


# ======================================
# VINDUE OG STIMULI
# ======================================
win = visual.Window(
    size=[1800, 1000],
    fullscr=True,
    color="black",
    units="height"
)

fixation = visual.TextStim(win, text="+", color="white", height=0.08)
question_stim = visual.TextStim(
    win, color="white", height=0.04, pos=(0, -0.38), wrapWidth=1.5
)

# ======================================
# INSTRUKTIONER
# ======================================
show_message(
    win,
    "Du vil gennemføre 6 blokke.\n\n"
    "I hver blok ser du først 6 ansigter, som du skal forsøge at huske.\n"
    "Derefter vil du se 30 ansigter ét ad gangen.\n\n"
    f"'{yes_key}' = ja, det var et af de 6\n"
    f"'{no_key}' = nej, det var ikke et af de 6\n\n"
    "Efter hvert svar skal du angive, hvor sikker du er fra 1 til 10.\n\n"
    "Tryk på mellemrum for at starte.",
    key_list=["space", quit_key]
)

# ======================================
# BLOKKE
# ======================================
for block_num in range(1, n_blocks + 1):

    if block_num % 2 == 1:
        current_gender = "women"
        current_distractor_pool = available_women_distractor_images
        gender_text = "kvinder"
        target_identities = women_target_blocks[women_block_index]
        women_block_index += 1
    else:
        current_gender = "men"
        current_distractor_pool = available_men_distractor_images
        gender_text = "mænd"
        target_identities = men_target_blocks[men_block_index]
        men_block_index += 1

    # ======================================
    # OLD TRIALS
    # uden tilbagelægning blandt target-billeder
    # ======================================
    old_candidates = []
    for ident in target_identities:
        for angle in ["S", "HL", "FL"]:
            old_candidates.append({
                "identity": ident,
                "angle": angle,
                "correct_answer": "yes",
                "status": "old",
                "file": identity_dict[ident][angle]
            })

    if n_old_trials > len(old_candidates):
        raise ValueError(
            f"n_old_trials er sat til {n_old_trials}, men der findes kun "
            f"{len(old_candidates)} gamle target-billeder uden tilbagelægning."
        )

    old_trials = balanced_angle_sample(old_candidates, n_old_trials)

    # ======================================
    # NEW TRIALS / DISTRACTORS
    # kvinder: ingen genbrug nødvendigt
    # mænd: i sidste mande-blok genbruges 9 distractors fra første mande-blok
    # ======================================
    if current_gender == "women":
        if len(current_distractor_pool) < n_new_trials:
            raise ValueError(
                f"Der er ikke nok ledige kvinde-distractor-billeder i blok {block_num}."
            )

        chosen_distractor_images = balanced_angle_sample(current_distractor_pool, n_new_trials)

        for img in chosen_distractor_images:
            current_distractor_pool.remove(img)

    else:
        # mande-blokke er blok 2, 4 og 6
        if block_num in [2, 4]:
            if len(current_distractor_pool) < n_new_trials:
                raise ValueError(
                    f"Der er ikke nok ledige mande-distractor-billeder i blok {block_num}."
                )

            chosen_distractor_images = balanced_angle_sample(current_distractor_pool, n_new_trials)

            for img in chosen_distractor_images:
                current_distractor_pool.remove(img)

            if block_num == 2:
                male_block1_distractors = chosen_distractor_images.copy()

        elif block_num == 6:
            # brug alle resterende unikke mande-distractors
            unique_remaining = current_distractor_pool.copy()
            n_unique = len(unique_remaining)
            n_extra_needed = n_new_trials - n_unique

            if n_extra_needed < 0:
                n_extra_needed = 0

            if n_extra_needed > len(male_block1_distractors):
                raise ValueError(
                    f"Der mangler {n_extra_needed} genbrugte distractors, "
                    f"men første mande-blok har kun {len(male_block1_distractors)}."
                )

            reused_from_first_block = random.sample(male_block1_distractors, n_extra_needed)
            chosen_distractor_images = unique_remaining + reused_from_first_block

            for img in unique_remaining:
                current_distractor_pool.remove(img)

            if len(chosen_distractor_images) != n_new_trials:
                raise ValueError(
                    f"Blok {block_num}: antal mande-distractors blev "
                    f"{len(chosen_distractor_images)} i stedet for {n_new_trials}."
                )
        else:
            raise ValueError(f"Uventet mande-blok: {block_num}")

    new_trials = []
    for img in chosen_distractor_images:
        new_trials.append({
            "identity": img["identity"],
            "angle": img["angle"],
            "correct_answer": "no",
            "status": "new",
            "file": img["file"]
        })

    test_trials = old_trials + new_trials
    random.shuffle(test_trials)

    # ======================================
    # BLOK-INTRO
    # ======================================
    show_message(
        win,
        f"Blok {block_num} af {n_blocks}\n\n"
        f"I denne blok ser du kun {gender_text}.\n\n"
        "Tryk på mellemrum for at starte indlæringsfasen.",
        key_list=["space", quit_key]
    )
    
    trigger(TRIGGERS["block_start"])
    
    fixation.draw()
    win.flip()
    safe_wait(fixation_duration)

    positions = [
        (-0.5,  0.25), (0,  0.25), (0.5,  0.25),
        (-0.5, -0.25), (0, -0.25), (0.5, -0.25)
    ]

    images = []
    for i, ident in enumerate(target_identities):
        img = visual.ImageStim(
            win,
            image=str(identity_dict[ident]["S"]),
            pos=positions[i],
            size=(0.35, 0.44)
        )
        images.append(img)

    for img in images:
        img.draw()
    
    win.callOnFlip(trigger, TRIGGERS["study_onset"])
    win.flip()
    safe_wait(study_face_duration)

    win.flip()
    safe_wait(iti_duration)

    show_message(
        win,
        "Indlæringsfasen er færdig.\n\n"
        "Nu starter testen.\n\n"
        f"Husk:\n'{yes_key}' = ja\n'{no_key}' = nej\n\n"
        "Tryk på mellemrum for at starte testen.",
        key_list=["space", quit_key]
    )

    # ======================================
    # TESTTRIALS
    # ======================================
    for trial_num, trial in enumerate(test_trials, start=1):
        event.clearEvents(eventType="keyboard")

        fixation.draw()
        win.flip()
        safe_wait(fixation_duration)

        face_stim = visual.ImageStim(
            win,
            image=str(trial["file"]),
            size=(0.4, 0.5)
        )

        question_stim.text = (
            f"Var dette et af de 6 ansigter?\n"
            f"Tryk '{yes_key}' for ja og '{no_key}' for nej"
        )

        response_clock = core.Clock()
        stimulus_trigger_sent = False
        while True:
            face_stim.draw()
            question_stim.draw()
            if not stimulus_trigger_sent:
                if trial["correct_answer"] == "old":
                    win.callOnFlip(trigger, TRIGGERS["test_old_onset"])
                    stimulus_trigger_sent = True
                else:
                    win.callOnFlip(trigger, TRIGGERS["test_new_onset"])
                    stimulus_trigger_sent = True
            win.flip()

            keys = event.getKeys(
                keyList=[yes_key, no_key, quit_key],
                timeStamped=response_clock
            )
            if keys:
                key, rt = keys[0]
                if key == quit_key:
                    quit_experiment()
                break

        if key == yes_key:
            old_new_response = "yes"
        else:
            old_new_response = "no"
        
        if old_new_response == "yes":
            trigger(TRIGGERS["response_yes"])
        else:
            trigger(TRIGGERS["response_no"])
    
        correct = int(old_new_response == trial["correct_answer"])

        x = 5

        rating_box = visual.Rect(
            win,
            width=0.10,
            height=0.10,
            fillColor="lightgrey",
            lineColor="grey",
            pos=(0, 0)
        )

        rating = visual.TextStim(
            win,
            text=str(x),
            pos=(0, 0),
            height=0.04,
            color="black"
        )

        rating_clock = core.Clock()
        confidence = x
        rating_rt = None

        conf = visual.TextStim(
            win,
            text="Confidence rating:",
            pos=(0, 0.2),
            height=0.04
        )

        conf_inst = visual.TextStim(
            win,
            text="Tryk højre pil for +1 og venstre pil for -1",
            pos=(0, -0.2),
            height=0.04
        )

        event.clearEvents(eventType="keyboard")
        waiting = True
        confidence_trigger_sent = False
        
        while waiting:
            conf.draw()
            rating_box.draw()
            rating.draw()
            conf_inst.draw()
            
            if not confidence_trigger_sent:
                win.callOnFlip(trigger, TRIGGERS["confidence_start"])
                confidence_trigger_sent = True
            win.flip()

            rating_keys = event.getKeys(
                keyList=[yes_key, no_key, "space", quit_key],
                timeStamped=rating_clock
            )

            if rating_keys:
                r_key, rating_rt = rating_keys[0]

                if r_key == quit_key:
                    quit_experiment()

                if r_key == yes_key and x > 1:
                    x -= 1
                elif r_key == no_key and x < 9:
                    x += 1
                elif r_key == "space":
                    confidence = x
                    trigger(TRIGGERS["confidence_confirm"]+confidence-1)
                    waiting = False

            rating.text = str(x)

        results.append({
            "participant": participant,
            "block_num": block_num,
            "block_gender": current_gender,
            "trial_num": trial_num,
            "identity": trial["identity"],
            "angle": trial["angle"],
            "status": trial["status"],
            "correct_answer": trial["correct_answer"],
            "response": old_new_response,
            "correct": correct,
            "confidence": confidence,
            "response_rt": rt,
            "rating_rt": rating_rt,
            "file_name": trial["file"].name
        })

        save_results()

        win.flip()
        safe_wait(iti_duration)
    
    trigger(TRIGGERS["block_end"])
    
    if block_num < n_blocks:
        show_message(
            win,
            f"Blok {block_num} er færdig.\n\nTryk på mellemrum for næste blok.",
            key_list=["space", quit_key]
        )
    
# ======================================
# GEM DATA
# ======================================
save_results()

# ======================================
# SLUTSKÆRM
# ======================================
show_message(
    win,
    "Opgaven er færdig.\n\nTak for din deltagelse.\n\nTryk på mellemrum for at lukke.",
    key_list=["space", quit_key]
)

save_results()
if port.is_open:
    port.close()
win.close()
core.quit()