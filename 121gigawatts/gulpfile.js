const {execFile} = require('node:child_process');
const {createHash} = require('node:crypto');
const {mkdtemp, readFile, rename, rm} = require('node:fs/promises');
const {join} = require('node:path');
const {promisify} = require('node:util');

const {series, watch, src, dest, parallel} = require('gulp');
const pump = require('pump');

// gulp plugins and utils
const livereload = require('gulp-livereload');
const postcss = require('gulp-postcss');
const zip = require('gulp-zip');
const concat = require('gulp-concat');
const uglify = require('gulp-uglify');
const beeper = require('beeper');

// postcss plugins
const autoprefixer = require('autoprefixer');
const colorFunction = require('postcss-color-function');
const cssnano = require('cssnano');
const customProperties = require('postcss-custom-properties');
const easyimport = require('postcss-easy-import');

function serve(done) {
    livereload.listen();
    done();
}

const handleError = (done) => {
    return function (err) {
        if (err) {
            beeper();
        }
        return done(err);
    };
};

function hbs(done) {
    pump([
        src(['*.hbs', 'partials/**/*.hbs']),
        livereload()
    ], handleError(done));
}

function css(done) {
    pump([
        src('assets/css/*.css', {sourcemaps: true}),
        postcss([
            easyimport,
            customProperties({preserve: false}),
            colorFunction(),
            autoprefixer(),
            cssnano()
        ]),
        dest('assets/built/', {sourcemaps: '.'}),
        livereload()
    ], handleError(done));
}

function js(done) {
    pump([
        src([
            // pull in lib files first so our own code can depend on it
            'assets/js/lib/*.js',
            'assets/js/*.js'
        ], {sourcemaps: true}),
        concat('casper.js'),
        uglify(),
        dest('assets/built/', {sourcemaps: '.'}),
        livereload()
    ], handleError(done));
}

const run = promisify(execFile);
const pdfViewerVersion = '6.5.438';
const pdfViewerSha256 = 'fcbe9ba21d9911843e3502adc178a7f549a524a4055f887bedc942e5490c6ba1';

async function pdfViewer() {
    const staging = await mkdtemp('assets/.pdfjs-');
    try {
        const download = join(staging, 'pdfjs.zip');
        const viewer = join(staging, 'viewer');
        const url = `https://github.com/mozilla/pdf.js/releases/download/v${pdfViewerVersion}/pdfjs-${pdfViewerVersion}-dist.zip`;
        await run('curl', ['--fail', '--location', '--silent', '--show-error', '--max-time', '45', '--output', download, url]);

        const checksum = createHash('sha256').update(await readFile(download)).digest('hex');
        if (checksum !== pdfViewerSha256) {
            throw new Error(`PDF.js ${pdfViewerVersion} download failed SHA-256 verification`);
        }

        // Keep the viewer and its worker from the same upstream release.
        await run('unzip', ['-q', download, '-d', viewer]);
        await rm('assets/pdfjs', {recursive: true, force: true});
        await rename(viewer, 'assets/pdfjs');
    } finally {
        await rm(staging, {recursive: true, force: true});
    }
}

function zipper(done) {
    const filename = require('./package.json').name + '.zip';

    pump([
        src([
            '*.hbs', 'partials/**', 'assets/**', 'package.json', 'LICENSE'
        ], {base: '.'}),
        zip(filename),
        dest('dist/')
    ], handleError(done));
}

const cssWatcher = () => watch('assets/css/**', css);
const hbsWatcher = () => watch(['*.hbs', 'partials/**/*.hbs'], hbs);
const watcher = parallel(cssWatcher, hbsWatcher);
const build = series(css, js);

exports.build = build;
exports.zip = series(parallel(build, pdfViewer), zipper);
exports.default = series(build, serve, watcher);

