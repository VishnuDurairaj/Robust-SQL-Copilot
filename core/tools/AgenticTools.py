import sys
sys.dont_write_bytecode =True
import os
import openai
import requests
from typing import List
from openai import OpenAI
from pydantic import BaseModel
from pydantic import BaseModel, Field
from core.models import OpenAIVissionModel
from concurrent.futures import ThreadPoolExecutor

openai_key = os.getenv("OPENAI_API_KEY")

#Initialize models
vision_model = OpenAIVissionModel()

# Initialize the OpenAI client
client = openai.OpenAI(api_key=openai_key)

class DescribePlots(BaseModel):
    """
    Use this tool to get insights from a visual and store it in a text file.
    """

    reasoning :List[str] = Field(description="Why you are using this tool")

    plots_path: str = Field(
        ..., description="A folder path which contains all the visuals"
    )
    project_folder_path : str = Field(description="Provide the main project folder path to save the visual insights")

    def get_insights(self, plot, question):
        print("*Getting Insights From* : ", plot)
        insights = vision_model.get_output(question=question, image_path=os.path.join(self.plots_path, plot), model="gpt-4o", api_key=openai_key)
        return f"Plot: {plot}\nInsights: \n{insights}\n\n------------------------------------------\n\n"

    def run(self):
        question = "You are provided with a plot from a data analysis. Extract all important actionable insights that can help improve the business."
        result_text = ""

        try:
            all_plots = os.listdir(self.plots_path)
            
            # Create a thread pool executor for parallel execution
            with ThreadPoolExecutor() as executor:
                futures = [
                    executor.submit(self.get_insights, plot, question)
                    for plot in all_plots
                ]
                results = [future.result() for future in futures]

            for result in results:
                result_text += result

            with open(f"{self.project_folder_path}/visual_insights.txt","w") as f:
                f.write(result_text)

            return "All the visual insights are stored in visual_insights.txt file"

        except Exception as e:
            return f"An error occurred while executing the file: {str(e)}"
        
# Image Generator

class ImageGenerator(BaseModel):

    "Use this tool to create an illustration based on a description and store it in the `illustrations` folder"

    reasoning :List[str] = Field(description="Why you are using this tool")

    image_description: str = Field("Describe the illustration you want")

    target_folder : str =Field(description="Provide the folder path to store the images. Default folder : `illustrations`")

    file_name : str =Field(description="File name with proper extension",examples=["image.png"])

    def run(self):
        response = client.images.generate(
            model="dall-e-3",
            prompt=self.image_description,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url

        # Download the image and save it locally
        image_response = requests.get(image_url)
        if image_response.status_code == 200:
            with open(f'{self.target_folder}/{self.file_name}', 'wb') as f:
                f.write(image_response.content)
            return f"{self.target_folder}/{self.file_name}"
        else:
           return "Failed to create the image."