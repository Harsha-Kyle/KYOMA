with open('Kyoma/fast_router.py', 'r', encoding='utf-8') as f:
    text = f.read()

old = '"play_pause","next_track","previous_track","startfrombegin_track",'
new = '"play_pause","play","pause","next_track","previous_track","startfrombegin_track",'
text = text.replace(old, new)

old_list = '"close_application",'
new_list = '"close_application","add_reminder","list_active_reminders",'
text = text.replace(old_list, new_list)

text = text.replace('"✅"', '"[PASS]"').replace('"❌"', '"[FAIL]"')

with open('Kyoma/fast_router.py', 'w', encoding='utf-8') as f:
    f.write(text)
print("Updated fast_router test tools successfully.")
