
import os
import re
import subprocess

APP_FILE = "app.py"
ADMIN_TEMPLATE = "templates/admin/subscribers.html"

def run(cmd):
    print(f"Running: {cmd}")
    subprocess.run(cmd, shell=True)

def update_template():
    print("--- Updating Admin Template ---")
    with open(ADMIN_TEMPLATE, "w") as f:
        f.write("""{% extends 'admin/base_admin.html' %}

{% block admin_content %}
<div class="mb-8 flex items-center justify-between">
    <h1 class="text-xl font-bold text-white uppercase tracking-widest">Intelligence Feed Subscribers</h1>
    <div class="text-zinc-500 font-mono text-xs">Total Segment: {{ subscribers|length }}</div>
</div>

<div class="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden shadow-2xl">
    <table class="w-full text-left">
        <thead>
            <tr class="bg-zinc-950 text-[10px] font-black uppercase tracking-widest text-zinc-500 border-b border-zinc-800">
                <th class="px-6 py-4">ID</th>
                <th class="px-6 py-4">Email Address</th>
                <th class="px-6 py-4">Status</th>
                <th class="px-6 py-4">Joined At</th>
                <th class="px-6 py-4">Action</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
            {% for sub in subscribers %}
            <tr class="hover:bg-zinc-800/30 transition-colors">
                <td class="px-6 py-4 text-zinc-600 font-mono text-xs">{{ sub.id }}</td>
                <td class="px-6 py-4 text-zinc-200 font-bold">{{ sub.email }}</td>
                <td class="px-6 py-4">
                    <span class="px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-widest {% if sub.status == 'ACTIVE' %}bg-green-600/20 text-green-500{% else %}bg-red-600/20 text-red-500{% endif %}">
                        {{ sub.status }}
                    </span>
                </td>
                <td class="px-6 py-4 text-zinc-500 text-xs">{{ sub.created_at }}</td>
                <td class="px-6 py-4">
                    <form action="{{ url_for('delete_subscriber', id=sub.id) }}" method="POST" onsubmit="return confirm('Are you sure you want to delete this subscriber?');">
                        <button type="submit" class="text-red-500 hover:text-red-400 font-bold text-[10px] uppercase tracking-wider">
                            Delete
                        </button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
""")
    print("Template updated.")

def patch_app_py():
    print("--- Patching app.py with Delete Route ---")
    with open(APP_FILE, 'r') as f:
        content = f.read()

    # Check if route already exists
    if "def delete_subscriber(" in content:
        print("Route already exists. Skipping.")
        return

    # Append new route
    new_route = """
@app.route('/admin/subscribers/delete/<int:id>', methods=['POST'])
@login_required
def delete_subscriber(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM subscribers WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Subscriber deleted.')
    return redirect(url_for('admin_subscribers'))
"""
    # Insert before __main__ or at end
    if "if __name__ == '__main__':" in content:
        content = content.replace("if __name__ == '__main__':", new_route + "\nif __name__ == '__main__':")
    else:
        content += "\n" + new_route

    with open(APP_FILE, 'w') as f:
        f.write(content)
    print("app.py patched.")

if __name__ == "__main__":
    update_template()
    patch_app_py()
    print("--- Restarting Service ---")
    run("sudo supervisorctl restart dailyaiwire")
    print("DONE! Delete functionality added.")
