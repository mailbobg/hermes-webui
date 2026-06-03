/* Hermes WebUI — Windows console launcher (portable/green build).
 *
 * Cross-compiled to Hermes.exe from macOS/Linux with:
 *   zig cc -target x86_64-windows-gnu launcher.c -o Hermes.exe -lshell32
 *
 * Lives at the portable root next to python\, webui\, agent\. It:
 *   1. Points the WebUI at the bundled embedded Python and agent source.
 *   2. Starts python\python.exe webui\server.py inside a Job object.
 *   3. Opens the default browser at the WebUI URL.
 *   4. Blocks until the server exits; closing this console window terminates
 *      the whole process tree (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE), so nothing
 *      lingers.
 */
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    char exePath[MAX_PATH];
    GetModuleFileNameA(NULL, exePath, MAX_PATH);

    char dir[MAX_PATH];
    snprintf(dir, sizeof(dir), "%s", exePath);
    char *slash = strrchr(dir, '\\');
    if (slash) *slash = '\0';

    char python[MAX_PATH * 2], webui[MAX_PATH * 2], server[MAX_PATH * 2], agent[MAX_PATH * 2];
    snprintf(python, sizeof(python), "%s\\python\\python.exe", dir);
    snprintf(webui,  sizeof(webui),  "%s\\webui", dir);
    snprintf(server, sizeof(server), "%s\\webui\\server.py", dir);
    snprintf(agent,  sizeof(agent),  "%s\\agent", dir);

    /* config.py (_discover_agent_dir) prefers HERMES_WEBUI_AGENT_DIR and injects
     * it onto the front of sys.path so the WebUI can import the agent in-process.
     * No separate agent venv exists — all deps live in the embedded interpreter. */
    SetEnvironmentVariableA("HERMES_WEBUI_AGENT_DIR", agent);
    SetEnvironmentVariableA("HERMES_WEBUI_PYTHON", python);

    HANDLE job = CreateJobObjectA(NULL, NULL);
    if (job) {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli;
        memset(&jeli, 0, sizeof(jeli));
        jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(job, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));
    }

    char cmdline[MAX_PATH * 4];
    snprintf(cmdline, sizeof(cmdline), "\"%s\" \"%s\"", python, server);

    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    memset(&pi, 0, sizeof(pi));

    printf("Starting Hermes WebUI...\n");
    fflush(stdout);

    if (!CreateProcessA(NULL, cmdline, NULL, NULL, FALSE,
                        CREATE_SUSPENDED, NULL, webui, &si, &pi)) {
        printf("ERROR: failed to start server (error %lu)\n", (unsigned long)GetLastError());
        printf("Looked for: %s\n", python);
        printf("Press Enter to exit.\n");
        getchar();
        return 1;
    }
    if (job) AssignProcessToJobObject(job, pi.hProcess);
    ResumeThread(pi.hThread);

    /* Honor HERMES_WEBUI_PORT (default 8787), same as the WebUI/server reads it,
     * so the launched URL never drifts from the actual bind port. */
    char port[16] = "8787";
    GetEnvironmentVariableA("HERMES_WEBUI_PORT", port, sizeof(port));
    char url[64];
    snprintf(url, sizeof(url), "http://127.0.0.1:%s/", port);

    Sleep(4000);
    ShellExecuteA(NULL, "open", url, NULL, NULL, SW_SHOWNORMAL);
    printf("Hermes is running at %s\n", url);
    printf("Close this window to stop Hermes.\n");
    fflush(stdout);

    WaitForSingleObject(pi.hProcess, INFINITE);
    if (job) CloseHandle(job);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
