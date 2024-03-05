# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
#
# Copyright 2021 The NiPreps Developers <nipreps@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# We support and encourage derived works from this project, please read
# about our expectations at
#
#     https://www.nipreps.org/community/licensing/
#
"""ReportCapableInterfaces for segmentation tools."""

import os
import re
import time
from collections import Counter

from nipype.interfaces import fsl
from nipype.interfaces.base import (
    BaseInterfaceInputSpec,
    Directory,
    File,
    InputMultiObject,
    SimpleInterface,
    Str,
    TraitedSpec,
    isdefined,
    traits,
)
from nipype.interfaces.mixins import reporting
from nireports.interfaces.reporting import base as nrb
from niworkflows import NIWORKFLOWS_LOG
from smriprep.interfaces.freesurfer import ReconAll


SUBJECT_TEMPLATE = """\
\t<ul class="elem-desc">
\t\t<li>Subject ID: {subject_id}</li>
\t\t<li>Structural images: {n_t1s:d} T1-weighted {t2w}</li>
\t\t<li>Functional series: {n_bold:d}</li>
{tasks}
\t\t<li>Standard output spaces: {std_spaces}</li>
\t\t<li>Non-standard output spaces: {nstd_spaces}</li>
\t\t<li>FreeSurfer reconstruction: {freesurfer_status}</li>
\t</ul>
"""

FUNCTIONAL_TEMPLATE = """\
\t\t<details open>
\t\t<summary>Summary</summary>
\t\t<ul class="elem-desc">
\t\t\t<li>Original orientation: {ornt}</li>
\t\t\t<li>Repetition time (TR): {tr:.03g}s</li>
\t\t\t<li>Phase-encoding (PE) direction: {pedir}</li>
\t\t\t<li>{multiecho}</li>
\t\t\t<li>Slice timing correction: {stc}</li>
\t\t\t<li>Susceptibility distortion correction: {sdc}</li>
\t\t\t<li>Registration: {registration}</li>
\t\t\t<li>Non-steady-state volumes: {dummy_scan_desc}</li>
\t\t</ul>
\t\t</details>
"""

ABOUT_TEMPLATE = """\t<ul>
\t\t<li>fMRIPrep version: {version}</li>
\t\t<li>fMRIPrep command: <code>{command}</code></li>
\t\t<li>Date preprocessed: {date}</li>
\t</ul>
</div>
"""


class SummaryOutputSpec(TraitedSpec):
    out_report = File(exists=True, desc="HTML segment containing summary")


class SummaryInterface(SimpleInterface):
    output_spec = SummaryOutputSpec

    def _run_interface(self, runtime):
        segment = self._generate_segment()
        fname = os.path.join(runtime.cwd, "report.html")
        with open(fname, "w") as fobj:
            fobj.write(segment)
        self._results["out_report"] = fname
        return runtime

    def _generate_segment(self):
        raise NotImplementedError


class _MELODICInputSpecRPT(nrb._SVGReportCapableInputSpec, fsl.model.MELODICInputSpec):
    out_report = File(
        "melodic_reportlet.svg",
        usedefault=True,
        desc="Filename for the visual report generated by Nipype.",
    )
    report_mask = File(
        desc=(
            "Mask used to draw the outline on the reportlet. "
            "If not set the mask will be derived from the data."
        ),
    )


class _MELODICOutputSpecRPT(
    reporting.ReportCapableOutputSpec,
    fsl.model.MELODICOutputSpec,
):
    pass


class MELODICRPT(fsl.MELODIC):
    """Create a reportlet for MELODIC outputs."""

    input_spec = _MELODICInputSpecRPT
    output_spec = _MELODICOutputSpecRPT
    _out_report = None

    def __init__(self, generate_report=False, **kwargs):
        """Create the reportlet."""
        super().__init__(**kwargs)
        self.generate_report = generate_report

    def _post_run_hook(self, runtime):
        # Run _post_run_hook of super class
        runtime = super()._post_run_hook(runtime)
        # leave early if there's nothing to do
        if not self.generate_report:
            return runtime

        NIWORKFLOWS_LOG.info("Generating report for MELODIC.")
        _melodic_dir = runtime.cwd
        if isdefined(self.inputs.out_dir):
            _melodic_dir = self.inputs.out_dir
        self._melodic_dir = os.path.abspath(_melodic_dir)

        self._out_report = self.inputs.out_report
        if not os.path.isabs(self._out_report):
            self._out_report = os.path.abspath(os.path.join(runtime.cwd, self._out_report))

        mix = os.path.join(self._melodic_dir, "melodic_mix")
        if not os.path.exists(mix):
            NIWORKFLOWS_LOG.warning("MELODIC outputs not found, assuming it didn't converge.")
            self._out_report = self._out_report.replace(".svg", ".html")
            snippet = "<h4>MELODIC did not converge, no output</h4>"
            with open(self._out_report, "w") as fobj:
                fobj.write(snippet)
            return runtime

        self._generate_report()
        return runtime

    def _list_outputs(self):
        try:
            outputs = super()._list_outputs()
        except NotImplementedError:
            outputs = {}
        if self._out_report is not None:
            outputs["out_report"] = self._out_report
        return outputs

    def _generate_report(self):
        from niworkflows.viz.utils import plot_melodic_components

        plot_melodic_components(
            melodic_dir=self._melodic_dir,
            in_file=self.inputs.in_files[0],
            tr=self.inputs.tr_sec,
            out_file=self._out_report,
            compress=self.inputs.compress_report,
            report_mask=self.inputs.report_mask,
        )


class _ICAAROMAInputSpecRPT(
    nrb._SVGReportCapableInputSpec,
    fsl.aroma.ICA_AROMAInputSpec,
):
    out_report = File(
        "ica_aroma_reportlet.svg",
        usedefault=True,
        desc="Filename for the visual" " report generated " "by Nipype.",
    )
    report_mask = File(
        desc=(
            "Mask used to draw the outline on the reportlet. "
            "If not set the mask will be derived from the data."
        ),
    )


class _ICAAROMAOutputSpecRPT(
    reporting.ReportCapableOutputSpec,
    fsl.aroma.ICA_AROMAOutputSpec,
):
    pass


class ICAAROMARPT(reporting.ReportCapableInterface, fsl.ICA_AROMA):
    """Create a reportlet for ICA-AROMA outputs."""

    input_spec = _ICAAROMAInputSpecRPT
    output_spec = _ICAAROMAOutputSpecRPT

    def _generate_report(self):
        from niworkflows.viz.utils import plot_melodic_components

        plot_melodic_components(
            melodic_dir=self.inputs.melodic_dir,
            in_file=self.inputs.in_file,
            out_file=self.inputs.out_report,
            compress=self.inputs.compress_report,
            report_mask=self.inputs.report_mask,
            noise_components_file=self._noise_components_file,
        )

    def _post_run_hook(self, runtime):
        outputs = self.aggregate_outputs(runtime=runtime)
        self._noise_components_file = os.path.join(outputs.out_dir, "classified_motion_ICs.txt")

        NIWORKFLOWS_LOG.info("Generating report for ICA AROMA")

        return super()._post_run_hook(runtime)


class SubjectSummaryInputSpec(BaseInterfaceInputSpec):
    t1w = InputMultiObject(File(exists=True), desc="T1w structural images")
    t2w = InputMultiObject(File(exists=True), desc="T2w structural images")
    subjects_dir = Directory(desc="FreeSurfer subjects directory")
    subject_id = Str(desc="Subject ID")
    bold = InputMultiObject(
        traits.Either(File(exists=True), traits.List(File(exists=True))),
        desc="BOLD functional series",
    )
    std_spaces = traits.List(Str, desc="list of standard spaces")
    nstd_spaces = traits.List(Str, desc="list of non-standard spaces")


class SubjectSummaryOutputSpec(SummaryOutputSpec):
    # This exists to ensure that the summary is run prior to the first ReconAll
    # call, allowing a determination whether there is a pre-existing directory
    subject_id = Str(desc="FreeSurfer subject ID")


class SubjectSummary(SummaryInterface):
    input_spec = SubjectSummaryInputSpec
    output_spec = SubjectSummaryOutputSpec

    def _run_interface(self, runtime):
        if isdefined(self.inputs.subject_id):
            self._results["subject_id"] = self.inputs.subject_id
        return super()._run_interface(runtime)

    def _generate_segment(self):
        BIDS_NAME = re.compile(
            r"^(.*\/)?"
            "(?P<subject_id>sub-[a-zA-Z0-9]+)"
            "(_(?P<session_id>ses-[a-zA-Z0-9]+))?"
            "(_(?P<task_id>task-[a-zA-Z0-9]+))?"
            "(_(?P<acq_id>acq-[a-zA-Z0-9]+))?"
            "(_(?P<rec_id>rec-[a-zA-Z0-9]+))?"
            "(_(?P<run_id>run-[a-zA-Z0-9]+))?"
        )

        if not isdefined(self.inputs.subjects_dir):
            freesurfer_status = "Not run"
        else:
            recon = ReconAll(
                subjects_dir=self.inputs.subjects_dir,
                subject_id="sub-" + self.inputs.subject_id,
                T1_files=self.inputs.t1w,
                flags="-noskullstrip",
            )
            if recon.cmdline.startswith("echo"):
                freesurfer_status = "Pre-existing directory"
            else:
                freesurfer_status = "Run by fMRIPrep"

        t2w_seg = ""
        if self.inputs.t2w:
            t2w_seg = f"(+ {len(self.inputs.t2w):d} T2-weighted)"

        # Add list of tasks with number of runs
        bold_series = self.inputs.bold if isdefined(self.inputs.bold) else []
        bold_series = [s[0] if isinstance(s, list) else s for s in bold_series]

        counts = Counter(
            BIDS_NAME.search(series).groupdict()["task_id"][5:] for series in bold_series
        )

        tasks = ""
        if counts:
            header = '\t\t<ul class="elem-desc">'
            footer = "\t\t</ul>"
            lines = [
                "\t\t\t<li>Task: {task_id} ({n_runs:d} run{s})</li>".format(
                    task_id=task_id, n_runs=n_runs, s="" if n_runs == 1 else "s"
                )
                for task_id, n_runs in sorted(counts.items())
            ]
            tasks = "\n".join([header] + lines + [footer])

        return SUBJECT_TEMPLATE.format(
            subject_id=self.inputs.subject_id,
            n_t1s=len(self.inputs.t1w),
            t2w=t2w_seg,
            n_bold=len(bold_series),
            tasks=tasks,
            std_spaces=", ".join(self.inputs.std_spaces),
            nstd_spaces=", ".join(self.inputs.nstd_spaces),
            freesurfer_status=freesurfer_status,
        )


class AboutSummaryInputSpec(BaseInterfaceInputSpec):
    version = Str(desc="FMRIPREP version")
    command = Str(desc="FMRIPREP command")
    # Date not included - update timestamp only if version or command changes


class AboutSummary(SummaryInterface):
    input_spec = AboutSummaryInputSpec

    def _generate_segment(self):
        return ABOUT_TEMPLATE.format(
            version=self.inputs.version,
            command=self.inputs.command,
            date=time.strftime("%Y-%m-%d %H:%M:%S %z"),
        )
