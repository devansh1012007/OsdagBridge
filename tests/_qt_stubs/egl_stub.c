/* Minimal no-op EGL stub for headless (offscreen) Qt testing.
 *
 * The sandbox has no libEGL.so.1 (glvnd) system package and there is no
 * root access to install one.  PySide6's libQt6Gui links against EGL with
 * BIND_NOW, so the shared object must exist and export the EGL entry
 * points even though the "offscreen" QPA platform never calls them.
 * This stub provides those symbols; every function is a harmless no-op.
 */
void eglBindAPI(unsigned a) { (void)a; }
unsigned long eglChooseConfig(void *d, const int *a, void **c, int b, int *n) { (void)d;(void)a;(void)c;(void)b; if (n) *n = 0; return 0; }
void *eglCreateContext(void *d, void *c, void *s, const int *a) { (void)d;(void)c;(void)s;(void)a; return (void*)0; }
void *eglCreatePbufferSurface(void *d, void *c, const int *a) { (void)d;(void)c;(void)a; return (void*)0; }
void *eglCreateWindowSurface(void *d, void *c, void *w, const int *a) { (void)d;(void)c;(void)w;(void)a; return (void*)0; }
unsigned long eglDestroyContext(void *d, void *c) { (void)d;(void)c; return 1; }
unsigned long eglDestroySurface(void *d, void *s) { (void)d;(void)s; return 1; }
void *eglCreateImage(void *d, void *c, unsigned t, void *b, const int *a) { (void)d;(void)c;(void)t;(void)b;(void)a; return (void*)0; }
unsigned long eglDestroyImage(void *d, void *i) { (void)d;(void)i; return 1; }
unsigned long eglGetConfigAttrib(void *d, void *c, int a, int *v) { (void)d;(void)c;(void)a; if (v) *v = 0; return 0; }
unsigned long eglGetConfigs(void *d, void **c, int n, int *m) { (void)d;(void)c;(void)n; if (m) *m = 0; return 0; }
void *eglGetCurrentContext(void) { return (void*)0; }
void *eglGetCurrentDisplay(void) { return (void*)0; }
void *eglGetCurrentSurface(int r) { (void)r; return (void*)0; }
void *eglGetDisplay(void *n) { (void)n; return (void*)0; }
int eglGetError(void) { return 0x3000; }              /* EGL_SUCCESS */
void (*eglGetProcAddress(const char *p))(void) { (void)p; return (void (*)(void))0; }
unsigned long eglInitialize(void *d, int *ma, int *mi) { (void)d; if (ma) *ma = 0; if (mi) *mi = 0; return 0; }
unsigned long eglMakeCurrent(void *d, void *s, void *s2, void *c) { (void)d;(void)s;(void)s2;(void)c; return 0; }
unsigned long eglQueryContext(void *d, void *c, int a, int *v) { (void)d;(void)c;(void)a; if (v) *v = 0; return 0; }
const char *eglQueryString(void *d, int n) { (void)d;(void)n; return (const char*)0; }
unsigned long eglSwapBuffers(void *d, void *s) { (void)d;(void)s; return 0; }
unsigned long eglSwapInterval(void *d, int i) { (void)d;(void)i; return 0; }
unsigned long eglTerminate(void *d) { (void)d; return 1; }
unsigned long eglWaitGL(void) { return 1; }
unsigned long eglWaitNative(int e) { (void)e; return 1; }
