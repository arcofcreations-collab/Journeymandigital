import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, '/tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/challenger_eval_ws/_ref')
from ref_expenses import ExpensesApp
def create_app():
    return ExpensesApp(HERE)
