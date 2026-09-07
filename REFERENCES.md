# References

Accessed 2026-09-06 unless noted. Software versions are review targets; the exact version and model hash used for each analysis are also written into its result manifest.

## Course and local sources

- Zelik, K. E. (2026). *Project 1: Biomechanics of Human Movement (Fall 2026)*. Vanderbilt University. Local course handout, updated 2026-08-21.
- Zelik, K. E. (2026). *ME 3890/5890 & BME 3890/8901 - Biomechanics of Human Movement - Fall 2026*. Vanderbilt University. Local syllabus, updated 2026-08-21.
- Uchida, T. K., & Delp, S. L. (2021). *Biomechanics of Movement: The Science of Sports, Robotics, and Rehabilitation*. MIT Press. https://mitpress.mit.edu/9780262543397/biomechanics-of-movement/
- `Design Books/DESIGN_RESEARCH.md`. Local working product-research document. Its principles were reviewed; the unofficial book files named there were not used as evidence.

## Cornhole rules

- American Cornhole League. (2025/26). *Rules and Regulations: Layout*. https://www.iplaycornhole.com/about/acl-information/rules-regulations/layout
- American Cornhole League. (2026). *Basic Rules & Scoring*. https://www.iplaycornhole.com/basic-rules-scoring
- American Cornhole League. (2025/26). *Bags + Equipment*. https://www.iplaycornhole.com/about/acl-information/equipment-bags-boards

## Precision throwing and motor control

- Nasu, D., Matsuo, T., & Kadota, K. (2014). Two types of motor strategy for accurate dart throwing. *PLOS ONE, 9*(2), e88536. https://doi.org/10.1371/journal.pone.0088536
- Nasu, D., & Matsuo, T. (2015). Upper extremity kinematics for throwing accuracy: Comparison between different strategies in expert dart players. *International Journal of Sport and Health Science, 60*(1), 303-313. https://doi.org/10.5432/jjpehss.14047
- Tran, B. N., Yano, S., & Kondo, T. (2019). Coordination of human movements resulting in motor strategies exploited by skilled players during a throwing task. *PLOS ONE, 14*(10), e0223837. https://doi.org/10.1371/journal.pone.0223837
- Cohen, R. G., & Sternad, D. (2012). State space analysis of timing: Exploiting task redundancy to reduce sensitivity to timing. *Journal of Neurophysiology, 107*(2), 618-627. https://doi.org/10.1152/jn.00568.2011

## Markerless motion and camera geometry

- Stenum, J., Rossi, C., & Roemmich, R. T. (2021). Two-dimensional video-based analysis of human gait using pose estimation. *PLOS Computational Biology, 17*(4), e1008935. https://doi.org/10.1371/journal.pcbi.1008935
- Scott, B., Chadwick, E., McInnes, M., & Blana, D. (2023). Assessing single camera markerless motion capture during upper limb activities of daily living. *Gait & Posture, 106*, S184. https://doi.org/10.1016/j.gaitpost.2023.07.222
- Vanmechelen, I., Van Wonterghem, E., Aerts, J.-M., et al. (2024). Markerless motion analysis to assess reaching-sideways in individuals with dyskinetic cerebral palsy: A validity study. *Journal of Biomechanics, 173*, 112233. https://doi.org/10.1016/j.jbiomech.2024.112233
- Sih, B. L., Hubbard, M., & Williams, K. R. (2001). Correcting out-of-plane errors in two-dimensional imaging using nonimage-related information. *Journal of Biomechanics, 34*(2), 257-260. https://doi.org/10.1016/S0021-9290(00)00185-8
- Yokoi, T., & Okada, H. (1994). Quantification and a simple correction of perspective error in two-dimensional motion analysis of human movement. *Anthropological Science, 102*(3), 305-317. https://doi.org/10.1537/ase.102.305
- Kanko, R. M., Laende, E. K., Selbie, W. S., & Deluzio, K. J. (2021). Inter-session repeatability of markerless motion capture gait kinematics. *Journal of Biomechanics, 121*, 110422. https://doi.org/10.1016/j.jbiomech.2021.110422
- Kidzinski, L., Yang, B., Hicks, J. L., Rajagopal, A., Delp, S. L., & Schwartz, M. H. (2020). Deep neural networks enable quantitative movement analysis using single-camera videos. *Nature Communications, 11*, 4054. https://doi.org/10.1038/s41467-020-17807-z
- Ceseracciu, E., Sawacha, Z., & Cobelli, C. (2014). Comparison of markerless and marker-based motion capture technologies through simultaneous data collection during gait: Proof of concept. *PLOS ONE, 9*(3), e87640. https://doi.org/10.1371/journal.pone.0087640

## Signal processing and statistics

- Challis, J. H. (1999). A procedure for determining appropriate cutoff frequencies for filtering biomechanical data. *Journal of Applied Biomechanics, 15*(3), 303-317. https://doi.org/10.1123/jab.15.3.303
- Winter, D. A. (2009). *Biomechanics and Motor Control of Human Movement* (4th ed.). Wiley. https://doi.org/10.1002/9780470549148
- SciPy Developers. (2026). `scipy.signal.butter`. https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.butter.html
- SciPy Developers. (2026). `scipy.signal.sosfiltfilt`. https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html
- SciPy Developers. (2026). `scipy.stats.spearmanr`. https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html
- SciPy Developers. (2026). `scipy.stats.bootstrap`. https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html

## Open-source software reviewed

- Pagnon, D., & Kim, H. (2024). Sports2D: Compute 2D human pose and angles from a video or a webcam. *Journal of Open Source Software, 9*(101), 6849. https://doi.org/10.21105/joss.06849. Repository: https://github.com/davidpagnon/Sports2D. PyPI 0.8.34; reviewed HEAD `4392177d75dff43b4da60514d3766029201a5c5e`; BSD-3-Clause.
- Pagnon, D., Domalain, M., & Reveret, L. (2022). Pose2Sim: An open-source Python package for multiview markerless kinematics. *Journal of Open Source Software, 7*(79), 4362. https://doi.org/10.21105/joss.04362. Repository: https://github.com/perfanalytics/pose2sim. PyPI 0.10.49; reviewed HEAD `65bbb056fecb3e6a7dd6064dc561bc065bc74bb6`; BSD-3-Clause.
- Google. (2026). *MediaPipe Pose Landmarker*. https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/ Repository: https://github.com/google-ai-edge/mediapipe. PyPI 1.0.1; reviewed HEAD `c17b2a83e8944d2811889a2a08d629c20bcb6ed8`; Apache-2.0.
- Jiang, T., Lu, P., Zhang, L., et al. (2023). RTMPose: Real-time multi-person pose estimation based on MMPose. arXiv:2303.07399. https://arxiv.org/abs/2303.07399. MMPose repository: https://github.com/open-mmlab/mmpose. Version 1.3.2; reviewed HEAD `759b39c13fea6ba094afc1fa932f51dc1b11cbf9`; Apache-2.0.
- Mathis, A., Mamidanna, P., Cury, K. M., et al. (2018). DeepLabCut: Markerless pose estimation of user-defined body parts with deep learning. *Nature Neuroscience, 21*, 1281-1289. https://doi.org/10.1038/s41593-018-0209-y. Repository: https://github.com/DeepLabCut/DeepLabCut. Version 3.0.1; reviewed HEAD `53e95879b9a090ccd095c3f9c724e1ade4be8fb4`; LGPL-3.0-or-later.

## Platform and policy documentation

- Apple. (2026). *Human Interface Guidelines: Designing for macOS*. https://developer.apple.com/design/human-interface-guidelines/designing-for-macos/
- Apple. (2026). *Human Interface Guidelines: Sidebars*. https://developer.apple.com/design/human-interface-guidelines/sidebars
- Apple. (2026). *Human Interface Guidelines: Toolbars*. https://developer.apple.com/design/human-interface-guidelines/toolbars
- Apple. (2026). *Human Interface Guidelines: Accessibility*. https://developer.apple.com/design/human-interface-guidelines/accessibility/
- Apple. (2026). `NavigationSplitView`. https://developer.apple.com/documentation/swiftui/navigationsplitview
- Apple. (2026). `AVPlayer`. https://developer.apple.com/documentation/avfoundation/avplayer
- YouTube. (2026). *Terms of Service*, Permissions and Restrictions. https://www.youtube.com/t/terms

