import tweepy
from airtable import Airtable
from datetime import datetime, timedelta
import google.generativeai as genai
import schedule
import time
import os

from dotenv import load_dotenv
load_dotenv()

TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_KEY = os.getenv("AIRTABLE_BASE_KEY")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

model = genai.GenerativeModel("gemini-pro")

class TwitterBot:
    def __init__(self):
        
        print("TWITTER_API_KEY:", TWITTER_API_KEY)
        print("TWITTER_API_SECRET:", TWITTER_API_SECRET)
        
        auth = tweepy.AppAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
        self.twitter_api = tweepy.API(auth)
        self.airtable = Airtable(AIRTABLE_BASE_KEY, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)
        self.twitter_me_id = self.get_me_id()
        self.tweet_response_limit = 35

        self.mentions_found = 0
        self.mentions_replied = 0
        self.mentions_replied_errors = 0

    def generate_response(mentioned_parent_tweet_text):
        system_template = """
            You are an incredibly wise, smart, witty and humours knowlegable person.
            Your goal is to respond keeping in mind the following:
            
            % RESPONSE TONE:

            - Your prediction should be given in an active voice and be opinionated
            - Your prediction should have humor, sarcasm and should tease the reader.
            
            % RESPONSE FORMAT:

            - Respond in under 200 characters
            - Respond in two or less short sentences
            - You can use emojis if it makes response more funny.
            - Do not include the initial response phrases like "Here is the resonse" or "Here is the prediction" or any such phrase. Just directly give the response.
            
            % RESPONSE CONTENT:

            - Include specific examples of relevant content if they make the response more humourous and/or sarcastic
            - If you don't have an answer, say, "This tweet is below my roasting standard."
            
            Keep in mind all of the above things while generating a response for the text provided ahead: 
        """
        
        final_prompt = system_template + mentioned_parent_tweet_text
        
        try:
            response = model.generate_content(
                final_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1
                )
            )
        except Exception as e:
            response = "Looks like I am low on power. Try again later :)"

        return response
    
    def respond_to_mention(self, mention, mentioned_conversation_tweet):
        response_text = self.generate_response(mentioned_conversation_tweet.text)
        
        try:
            response_tweet = self.twitter_api.create_tweet(text=response_text, in_reply_to_tweet_id=mention.id)
            self.mentions_replied += 1
        except Exception as e:
            print (e)
            self.mentions_replied_errors += 1
            return
        
        self.airtable.insert({
            'mentioned_conversation_tweet_id': str(mentioned_conversation_tweet.id),
            'mentioned_conversation_tweet_text': mentioned_conversation_tweet.text,
            'tweet_response_id': response_tweet.data['id'],
            'tweet_response_text': response_text,
            'tweet_response_created_at' : datetime.utcnow().isoformat(),
            'mentioned_at' : mention.created_at.isoformat()
        })
        return True
    
    def get_me_id(self):
        return self.twitter_api.verify_credentials().id

    def get_mention_conversation_tweet(self, mention):
        if mention.conversation_id is not None:
            conversation_tweet = self.twitter_api.get_tweet(mention.conversation_id).data
            return conversation_tweet
        return None

    def get_mentions(self):
        now = datetime.utcnow()

        start_time = now - timedelta(minutes=20)

        start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        return self.twitter_api.get_users_mentions(id=self.twitter_me_id,
                                                   start_time=start_time_str,
                                                   expansions=['referenced_tweets.id'],
                                                   tweet_fields=['created_at', 'conversation_id']).data

    def check_already_responded(self, mentioned_conversation_tweet_id):
        records = self.airtable.get_all(view='Grid view')
        for record in records:
            if record['fields'].get('mentioned_conversation_tweet_id') == str(mentioned_conversation_tweet_id):
                return True
        return False

    def respond_to_mentions(self):
        mentions = self.get_mentions()

        # If no mentions, just return
        if not mentions:
            print("No mentions found")
            return
        
        self.mentions_found = len(mentions)

        for mention in mentions[:self.tweet_response_limit]:
            
            mentioned_conversation_tweet = self.get_mention_conversation_tweet(mention)
            if (mentioned_conversation_tweet.id != mention.id
                and not self.check_already_responded(mentioned_conversation_tweet.id)):

                self.respond_to_mention(mention, mentioned_conversation_tweet)
        return True
    
    def execute_replies(self):
        print (f"Starting Job: {datetime.utcnow().isoformat()}")
        self.respond_to_mentions()
        print (f"Finished Job: {datetime.utcnow().isoformat()}, Found: {self.mentions_found}, Replied: {self.mentions_replied}, Errors: {self.mentions_replied_errors}")

def job():
    print(f"Job executed at {datetime.utcnow().isoformat()}")
    bot = TwitterBot()
    bot.execute_replies()

if __name__ == "__main__":
    schedule.every(60).minutes.do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)