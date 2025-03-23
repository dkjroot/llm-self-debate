"""A script that makes LLM characters debate with each other"""
import random
import re
import json
from datetime import datetime
from openai import OpenAI


# Read a file into a string
def readfile(filename):
    try:
        with open(filename, 'r') as in_file:
            return ''.join(in_file.readlines()).strip()
    except FileNotFoundError:
        print("File not found:", filename)
        exit(1)


# Read a comma separated list file into a list
def readfile_tolist(filename):
    return readfile(filename).split(',')


# Read a json into a dict
def read_json(filename):
    try:
        with open(filename) as json_file:
            return json.load(json_file)
    except FileNotFoundError:
        print("File not found:", filename)
        exit(1)


# Print the last X iterations of the conversation
def print_conversation(conversation, iterations, outfile):
    # It doesn't matter whose conversation we look at
    with open(outfile, 'a') as out_file:
        for conversation_line in conversation[-iterations:]:
            print(conversation_line['content'])
            print("")
            out_file.write(conversation_line['content'] + "\n\n")


# Add a line as if the speaker said it (used in loading the initial conversation from file)
def manually_add_line(conversation, speaker_name, new_line):
    conversation.append({'role': speaker_name, 'content': new_line})


# Some models ignore the instruction not to hallucinate instructions, so this attempts to remove anything that's not speech
def remove_after_last_double_quote(s):
    quoted_string_pattern = r"\".*\""
    if not re.match(quoted_string_pattern, s):
        return s
    last_quote_index = s.rfind('"')
    if last_quote_index != -1:
        return s[:last_quote_index + 1]
    return s


# Get the next response from the requested persona, and update all the other conversations to suit
def progress_conversations(conversation, speaker_name, personas, system_prompt, client, config):
    response = get_response(speaker_name, personas, system_prompt, client, config, conversation)
    if response:
        conversation.append({'role': speaker_name, 'content': f"{speaker_name}: {response}"})


# Remove the character names from the 'role' in conversation, replacing speaker with 'assistant' and all other
# names with 'user'
def personalise_conversation(conversation, speaker_name):
    ret = []
    for line in conversation:
        if line['role'] == speaker_name:
            ret.append({'role': 'assistant', 'content': line['content']})
        else:
            ret.append({'role': 'user', 'content': line['content']})
    return ret


# Call the openai API to get a response from the requested persona
def get_response(speaker_name, personas, system_prompt, client, config, conversation):
    conversation_as_persona = personalise_conversation(conversation, speaker_name)
    built_system_prompt = personas[speaker_name]['fixed_prompt'] + personas[speaker_name]['fixed_prompt'] + \
                          system_prompt[
                              'rules'] + system_prompt['scenario_fixed'] + system_prompt['scenario_variable']
    conversation_with_prompt = [{'role': 'system', 'content': built_system_prompt}] + conversation_as_persona
    completion = client.chat.completions.create(
        model=config['model'],
        max_tokens=config['max_tokens'], temperature=config['temperature'], top_p=config['top_p'],
        messages=conversation_with_prompt)
    result = completion.choices[0].message.content.strip()
    for cur_persona in personas:
        result = result.replace(f"{cur_persona}: ", "")
    return remove_after_last_double_quote(result)


# Load the initial conversation
def load_initial_conversation(personas, conversation, outfile):
    # Now load the initial conversation
    with open("initial_conversation.txt", 'r') as file:
        rolling_line = ""
        cur_name = ""
        line_count = 0
        for line in file:
            line = line.strip()
            new_name = line.split(':')[0]
            if new_name in personas.keys():
                if cur_name:
                    manually_add_line(conversation, cur_name, rolling_line)
                    line_count += 1
                cur_name = new_name
                rolling_line = line
            else:
                rolling_line += line
        manually_add_line(conversation, cur_name, rolling_line)
        line_count += 1
        print_conversation(conversation, line_count, outfile)
        return cur_name


# Load the persona files
def load_personas(names_list):
    ret = {}
    for cur_name in names_list:
        cur_prompt = read_json(f"{cur_name}_prompt.json")
        ret[cur_name] = {'fixed_prompt': cur_prompt['fixed_prompt'],
                         'variable_prompt': cur_prompt['variable_prompt'],
                         'conversation': []
                         }
    return ret


# Choose the next speaker from speaker_order (by speaker_index, which this function will increment)
# Or if the next speaker in speaker_order is the same as the last speaker, choose the next (until we get a new speaker,
# or we exhaust speaker_order).  If speaker_order is exhausted, choose a random speaker who is not the same as the last
# speaker.  Returns speaker, speaker_index
def choose_speaker(last_speaker, speaker_order, persona_names, speaker_index):
    if speaker_index < len(speaker_order):
        speaker = speaker_order[speaker_index]
        speaker_index = speaker_index + 1
        while speaker == last_speaker:
            speaker = speaker_order[speaker_index]
            speaker_index = speaker_index + 1
    else:
        speaker = random.choices(persona_names, k=1)[0]
        while speaker == last_speaker:
            speaker = random.choices(persona_names, k=1)[0]
    return speaker, speaker_index


# Every <update_prompt_every_N_statements> times a character speaks, the variable part of their prompt will be updated
# by the LLM to try to achieve more dynamic conversation amongst the characters.
def update_persona_prompt(persona_name, personas, conversation, client, config):
    conversation_as_persona = personalise_conversation(conversation, persona_name)
    fixed_prompt = personas[persona_name]['fixed_prompt']
    variable_prompt = personas[persona_name]['variable_prompt']
    system_prompt = ("Read the conversation paying special attention "
                     f"to the lines written by {persona_name}.  Do not write a new line continuing the conversation."
                     f"Your job is to write a new LLM system prompt for the {persona_name} character."
                     f"The {persona_name} character currently has the following fixed prompt: \"{fixed_prompt}\" and "
                     f"the variable prompt: \"{variable_prompt}\".  In the light of the debate " 
                     "so far, how would you change the variable part of the system prompt to in order to keep "
                     "the conversation fresh and interesting, and reflect the character's "
                     "changing point of view and priorities? Respond with the new variable "
                     "prompt only. Write the response as if you're specifying a prompt for "
                     "another LLM, i.e. use \"you\" not \"I\" or the character name. "
                     "Do not write about your reasoning for the prompt, or prefix it in any way, "
                     f"write only the new variable prompt for the character {persona_name}.")

    # just for good measure...
    conversation_as_persona.append({'role': 'user',
                                    'content': system_prompt
                                    })

    conversation_with_prompt = [{'role': 'system', 'content': system_prompt}] + conversation_as_persona
    completion = client.chat.completions.create(
        model=config['model'],
        max_tokens=config['max_tokens'], temperature=config['temperature'], top_p=config['top_p'],
        messages=conversation_with_prompt)
    result = completion.choices[0].message.content.strip()
    if config['print_new_dynamic_prompts']:
        print(f"\n*** NEW PROMPT for {persona_name}: {result}\n")
    personas[persona_name]['variable_prompt'] = result


def update_scenario_prompt(system_prompt, conversation, client, config):
    fixed_prompt = system_prompt['scenario_fixed']
    variable_prompt = system_prompt['scenario_variable']
    this_system_prompt = ("Read the conversation paying special attention to how the scenario has developed over time."
                     "Do not write a new line continuing the conversation."
                     f"Your job is to write a new LLM system prompt for the scenario."
                     f"The scenario currently has the following fixed prompt: \"{fixed_prompt}\" and "
                     f"the variable prompt: \"{variable_prompt}\".  In the light of the debate " 
                     "so far, how would you change the variable part of the system prompt to in order to keep "
                     "the conversation fresh and interesting, and reflect the way the conversation has changed? "
                     "Respond with the new dynamic prompt only. Write the response as if you're specifying a prompt "
                     "for another LLM, i.e. use \"you\" not \"I\" or the character names. "
                     "Do not write about your reasoning for the prompt, or prefix it in any way, "
                     f"write only the new variable prompt for dynamic scenario.")

    # just for good measure...
    conversation_extended = conversation + [{'role': 'user', 'content': this_system_prompt}]
    conversation_with_prompt = [{'role': 'system', 'content': system_prompt}] + conversation_extended
    completion = client.chat.completions.create(
        model=config['model'],
        max_tokens=config['max_tokens'], temperature=config['temperature'], top_p=config['top_p'],
        messages=conversation_with_prompt)
    result = completion.choices[0].message.content.strip()
    if config['print_new_dynamic_prompts']:
        print(f"\n*** NEW SCENARIO PROMPT: {result}\n")
    system_prompt['scenario_variable'] = result


# This is mostly to prevent the use of globals, which will make restructuring the code easier later
def run_loop():
    # Load config and set up the api client etc.
    config = read_json("config.json")
    client = OpenAI(api_key=config['api_key'], base_url=config['base_url'])
    now = datetime.now()
    timestamp_str = f"{now:%Y%m%d%H%M%S}"
    outfile = f"./conversation_{timestamp_str}.txt"
    conversation = []
    update_character_every = config['update_dynamic_character_prompt_every_N_statements']
    update_scenario_every = config['new_dynamic_scenario_prompt_every_N_statements']

    # Load the system prompt (rules, fixed and variable scenario)
    system_prompt = read_json("system_prompt.json")

    # Load the personas for each of the speakers
    persona_names = readfile_tolist("names.txt")
    personas = load_personas(persona_names)

    # We can configure a specific speaker order - once exhausted, the next speaker will be chosen at random
    speaker_order = readfile_tolist("speaker_order.txt")
    speaker_index = 0

    # Load the initial conversation
    speaker = load_initial_conversation(personas, conversation, outfile)

    # Iterate on building the conversation speaker by speaker
    statement_num = 0
    while True:
            # Choose a speaker
            speaker, speaker_index = choose_speaker(speaker, speaker_order, persona_names, speaker_index)
            print(f"{speaker} is thinking...")

            # Consider updating the prompt for this speaker...
            count = sum(1 for line in conversation if line['role'] == speaker)
            if count % update_character_every == 0:
                update_persona_prompt(speaker, personas, conversation, client, config)

            # Progress the conversation
            progress_conversations(conversation, speaker, personas, system_prompt, client, config)

            # And print the new conversation line
            print_conversation(conversation, 1, outfile)

            statement_num = statement_num + 1
            # Consider updating the dynamic scenario prompt
            if count % update_scenario_every == 0:
                update_scenario_prompt(system_prompt, conversation, client, config)


# Main
if __name__ == "__main__":
    run_loop()
