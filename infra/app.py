import aws_cdk as cdk
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from stack import SemesterOSStack

app = cdk.App()
SemesterOSStack(app, "SemesterOS")
app.synth()
