# llm-self-debate
A python project where multiple LLM personalities debate each other

The idea is quite simple - set up multiple system prompts for different characters, and alternate between them, building up a conversation about a subject that you choose.  I want to make it so that you can intervene, and since I can't be bothered to make a UI that'll be by stopping the script and editing the text files!  

I think the tricky part will be getting something better than a circular conversation that never goes anywhere below the surface of the topic, because LLMs are very good at pretending they're not superficial, but they are basically pretty superficial.  Anyway, lets see how good we can make it.


# Requirements

Uses the openai api, so you need to have something to talk to, either an online service or run a local model in something like koboldcpp.  I like koboldcpp, I find it simple to use, and I can run a 70B llama 3.3 gguf locally with reasonable performance (not real time, but fast enough to get results, and you do need a good model for this experiment to be worth doing at all).  I use a smaller model for speed while I'm working on the script, but they output is not good.

Some models perform well and others are a pain to use in this format.  I'm finding the pure llama 3 models work fine.


# Goals

- [x] Alternate between multiple viewpoint characters.
- [x] Multiple characters each have their own personalities and agendas.
- [x] The conversation sent to the API uses 'assistant' for the current character, and 'user' for the other characters, so that the LLM thinks its own character is the only LLM in the conversation.
- [ ] Have the LLM update the character system prompts as the conversation progresses.
- [ ] Have the LLM update the scenario system prompt as the conversation progresses.


# How does it work?

names.txt contains a comma-separated list of the names of the characters in your debate.  e.g. "May,Ted,Pete,Ben,Violet"

Each character needs a Name_prompt.json, which is that character's initial system prompt.  e.g. May_prompt.json.  This contains two strings, 'fixed_prompt' that will always be used, and 'variable_prompt' that will be used as the initial variable prompt, but the LLM will update as the conversation progresses (this is an attempt to introduce some variance and freshness into the debate, otherwise the LLM tends to go round in circles). 

speaker_order.txt can be used to force a specific order for the speakers. When the script comes to the end of this list, it will choose a speaker at random. In both modes, it will avoid using the same speaker twice in a row.

system_prompt.json contains three strings: 'rules' where you can tune the behaviour of the LLM, 'scenario_fixed' where you can define non-variable parts of the debate scenario, and 'scenario_variable' which is an initial value for the part of the scenario that the LLM will be allowed to update as the debate progresses.

initial_conversation.txt contains the conversation that has occurred to date.  It's a good way to set an initial tone for the conversation.  You can also use this as a way to edit the conversation the characters have had so far - copy the conversation_(datetime).txt over initial_conversation.txt, edit anything you want to edit, then run the script again.

It's useful to have some starting point conversations prepared, and that's what prep_initial_conversation*.txt represent - copy one of those to initial_conversation.txt and start the script to begin a fresh debate.

Once you run the script, the characters will debate until you stop the script with ctrl+c.  The conversation will be written out to conversation_(datetime).txt

All the conversation.txt files follow the same format - character name colon "line", e.g. Ted: "Let's get started!"


# FAQ

Q: Why is this better than *other project*?
A: It probably isn't.  I just like to explore ideas myself.

 
