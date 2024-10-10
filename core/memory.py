
from CollabAgents.helper import print_colored

class ConversationBufferMemory:

    "In this memory type we Pass in all the messages from the conversation"

    def __init__(self) -> None:
         pass
         
    def prepare_memory(self,messages):

        return messages
    

class ConversationBufferWindowMemory:

    "In this memory type we Pass in the last N messages"

    def __init__(self,last_k=40) -> None:
         self.last_k = last_k
         
    def prepare_memory(self,messages):

        if len(messages[1:])>=self.last_k:

            print_colored("Updating Memory Using `ConversationBufferWindowMemory` Method....","olive")

            return messages[:1]+messages[-self.last_k:]
        else:
            return messages
    
class ConversationSummaryMemory:
    """In this memory type we recursively summarize the conversation every time the conversation exceeds some threshold of conversations/messages"""

    def __init__(self, number_of_messages=40, system_prompt=None, user_prompt=None) -> None:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.number_of_messages = number_of_messages
        self.buffer = []
        self.summary = ""

        if not self.system_prompt:
            self.system_prompt = "You are a world class AI assistant who excels at summarizing conversations. Your task is to provide concise yet comprehensive summary that capture the key points, context, and flow of the conversation. Do not include any explanations — Please provide just the summary in one or more paragraphs."

        if not self.user_prompt:
            self.user_prompt = "Please provide a concise summary of the given conversation. Focus on the main topics discussed, any decisions made, and the overall context. Ensure that your summary captures the essence of the conversation while being brief and easy to understand."

    def prepare_history(self, history):
        conversation_text = ""
        for turn in history:
            conversation_text += f"{turn['role']} : {turn['content']}\n"

        user_prompt = self.user_prompt + "\n\nBelow are the conversation messages:\n\n" + conversation_text

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        return messages
    
    async def prepare_memory(self, model, history):

        if len(history) >= self.number_of_messages:
            print_colored("Updating Memory Using `ConversationSummaryMemory` Method....","olive")
            messages = self.prepare_history(history)
            self.summary = await model.aget_summary(messages)
            return {"summary":self.summary,"messages":[]}
        else:
            return {"summary":"","messages":history}


class ConversationSummaryBufferMemory:
    """In this memory type we keep a buffer of recent interactions and compiles old ones into a summary"""

    def __init__(self, buffer_size: int = 40, system_prompt: str = None, user_prompt: str = None):
        self.buffer_size = buffer_size
        self.buffer = []
        self.summary: str = ""
        
        if not system_prompt:
            self.system_prompt = "You are an AI assistant tasked with maintaining a concise summary of a conversation. Update the existing summary with the new information, keeping the summary brief and relevant. If no existing summary is available, provide a concise summary of the conversation so far. Do not include any explanations — Please provide just the summary in one or more paragraphs."
        else:
            self.system_prompt = system_prompt

        if not user_prompt:
            self.user_prompt = "Summarize the conversation so far concisely, preserving key context while reducing the length of the conversation history."
        else:
            self.user_prompt = user_prompt

    def prepare_history(self, history):
        conversation_text = ""
        for turn in history:
            conversation_text += f"{turn['role']} : {turn['content']}\n"

        user_prompt = self.user_prompt + f"Current summary: {self.summary}\n\nRecent interactions:\n{conversation_text}"
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        return messages

    async def prepare_memory(self, model,history):

        for i in history:

            if len(self.buffer)<self.buffer_size:

                if i not in self.buffer:

                    self.buffer.append(i)

            else:

                print_colored("Updating Memory Using `ConversationSummaryBufferMemory` Method....","olive")

                messages = self.prepare_history(self.buffer[:self.buffer_size])

                conversation_summary = await model.aget_summary(messages)

                self.summary = conversation_summary

                response = {"summary":self.summary,"messages":history[len(self.buffer):]}

                self.buffer = []

                return response

        else:

            print_colored(f"Current Buffer Size : {len(self.buffer)}","red")

            return {"summary":"","messages":history}







