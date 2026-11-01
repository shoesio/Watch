#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <cstdlib>
static bool samsung_enabled() { return getenv("SAMSUNG_BRIDGE_SOCKET") != NULL; }
static std::string samsung_rpc(const char *cmd, double value, const char *url = "") {
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return "";
    timeval timeout = {1, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    sockaddr_un address = {}; address.sun_family = AF_UNIX;
    snprintf(address.sun_path, sizeof(address.sun_path), "%s", getenv("SAMSUNG_BRIDGE_SOCKET"));
    if (connect(fd, (sockaddr *)&address, sizeof(address)) < 0) { close(fd); return ""; }
    char number[64]; snprintf(number, sizeof(number), " %.6f ", value);
    std::string request = std::string(cmd) + number;
    const char *hex = "0123456789abcdef";
    for (const unsigned char *p = (const unsigned char *)url; *p; p++) { request += hex[*p >> 4]; request += hex[*p & 15]; }
    request += '\n';
    size_t sent = 0;
    while (sent < request.size()) { ssize_t n = send(fd, request.data()+sent, request.size()-sent, MSG_NOSIGNAL); if (n <= 0) break; sent += n; }
    char reply[512]; ssize_t n = recv(fd, reply, sizeof(reply)-1, 0); close(fd);
    if (n <= 0) return ""; reply[n] = 0; return reply;
}
static playback_info_t samsung_status() {
    playback_info_t info = {}; int ready=0, empty=1, full=0;
    std::string reply = samsung_rpc("status", 0);
    sscanf(reply.c_str(), "%lf %lf %f %d %d %d", &info.duration, &info.position, &info.rate, &ready, &empty, &full);
    info.ready_to_play = ready; info.playback_buffer_empty = empty; info.playback_buffer_full = full;
    info.playback_likely_to_keep_up = ready && !empty; info.seek_duration = info.duration;
    return info;
}
