# Use Python 3.12 as the base image
FROM python:3.12

# Set the working directory inside the container
WORKDIR /jupyternotebook

# Copy requirements and install Python dependencies (including Playwright)
COPY requirements.txt /jupyternotebook/

RUN pip install -r requirements.txt

# Install Jupyter Notebook
RUN pip install notebook

# Generate and setup Jupyter config
RUN jupyter notebook --generate-config && \
    echo "c.ServerApp.token = ''" >> /root/.jupyter/jupyter_notebook_config.py && \
    echo "c.ServerApp.password = ''" >> /root/.jupyter/jupyter_notebook_config.py && \
    echo "c.ServerApp.disable_check_xsrf = True" >> /root/.jupyter/jupyter_notebook_config.py && \
    echo "c.ServerApp.allow_origin = '*'" >> /root/.jupyter/jupyter_notebook_config.py && \
    echo "c.ServerApp.ip = '0.0.0.0'" >> /root/.jupyter/jupyter_notebook_config.py

# Expose the default Jupyter port
EXPOSE 8888

# Start Jupyter Notebook (consider switching to Jupyter Lab)
CMD ["sh", "-c", "jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser --allow-root > /dev/null 2>&1"]

