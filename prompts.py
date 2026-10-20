"""Original prompt wording, separated from transport for baseline comparisons."""

def personalise_conversation(conversation, speaker_name):
    ret = []
    for line in conversation:
        if line['role'] == speaker_name:
            ret.append({'role': 'assistant', 'content': line['content']})
        else:
            ret.append({'role': 'user', 'content': line['content']})
    return ret


def dialogue_messages(speaker_name, personas, system_prompt, conversation):
    conversation_as_persona = personalise_conversation(conversation, speaker_name)
    built_system_prompt = personas[speaker_name]['fixed_prompt'] + " " + personas[speaker_name]['variable_prompt'] + \
                          " " + system_prompt[
                              'rules'] + " " + system_prompt['scenario_fixed'] + " " + system_prompt[
                              'scenario_variable']
    conversation_with_prompt = [{'role': 'system', 'content': built_system_prompt}] + conversation_as_persona
    return conversation_with_prompt


def character_messages(persona_name, personas, conversation):
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
                     "changing point of view and priorities? Beware of the tendency to remove "
                     "all drama and interest from a conversation by normalising everyone's views towards the centre "
                     "- adjust the prompt in a way that maintains the differences that make for an interesting "
                     "conversation. Respond with the new variable prompt only. Write the response as if you're "
                     "specifying a prompt for another LLM, i.e. use \"you\" not \"I\" or the character name. "
                     "Do not write about your reasoning for the prompt, or prefix it in any way, "
                     f"write only the new variable prompt for the character {persona_name}.")

    return [{'role': 'system', 'content': system_prompt}] + conversation_as_persona + [{'role': 'user', 'content': system_prompt}]


def scenario_messages(system_prompt, conversation):
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

    transcript = '\n\n'.join(line['content'] for line in conversation)
    return [{'role': 'system', 'content': this_system_prompt}, {'role': 'user', 'content': transcript + '\n\n' + this_system_prompt}]
