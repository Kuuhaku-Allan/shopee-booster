import streamlit as st
import sys
has_dialog = hasattr(st, "dialog")
has_exp_dialog = hasattr(st, "experimental_dialog")
print(f"Has dialog: {has_dialog}, Has exp_dialog: {has_exp_dialog}")
